import re
import sys
import pandas as pd
from SharedInfo import cutterA, cutterB
from Util.SeqUtil import parseSeqByCutter
from DataStructure import RepeatSeqOutputInfo


class MultipleCutter:
    def __init__(self, sequence, seqStateList):
        self.seqStates = {"unMatch": 0, "union": 1, "intersection": 2}
        self.sequence = sequence
        self.seqLength = len(sequence)
        self.seqStateList = seqStateList
        self.seqStateSum = [0] * len(sequence)
        self.matchStateIdxList = []
        self.matchStateRepeatInfoList = []
        self.repeatFrgmentDf = None

    def getSeqStateSum(self):
        if len(self.seqStateList) == 2:
            for idx, value in enumerate(self.seqStateSum):
                self.seqStateSum[idx] = (
                    self.seqStateList[0][idx] + self.seqStateList[1][idx]
                )
        else:
            print("Number of seqState Error")
        return self.seqStateSum

    def getSeqStateInfo(self):
        unMatchState = filter(
            lambda x: x == self.seqStates["unMatch"], self.seqStateSum
        )
        unionState = filter(
            lambda x: (x == self.seqStates["union"])
            or (x == self.seqStates["intersection"]),
            self.seqStateSum,
        )
        intersectionState = filter(
            lambda x: x == self.seqStates["intersection"], self.seqStateSum
        )
        print(
            f"chr: {self.seqLength}\nunMatch: {len(list(unMatchState))}, union:{len(list(unionState))}, intersection:{len(list(intersectionState))}"
        )
        return unMatchState, unionState, intersectionState

    def getSpecificStateIdxList(self, stateName="union"):
        self.matchStateIdxList = []
        if stateName == "intersection":
            self.matchStateIdxList = [
                idx
                for idx, state in enumerate(self.seqStateSum)
                if state == self.seqStates[stateName]
            ]
        elif stateName == "union":
            self.matchStateIdxList = [
                idx
                for idx, state in enumerate(self.seqStateSum)
                if (
                    (state == self.seqStates[stateName])
                    or (state == self.seqStates["intersection"])
                )
            ]
        return self.matchStateIdxList

    def getSpecificStatePositionList(self):
        """
        idx+baseIdx < leng(matchStateRepeatInfoList)
        idx : 400
        baseIdx = 1
        baseIdx == (matchStateRepeatInfoList[idx+baseIdx] - matchStateRepeatInfoList[idx])
        """

        self.matchStateRepeatInfoList = []
        idx = 0
        while self.matchStateIdxList[idx] < self.seqLength:
            baseCount = 1
            while (idx + baseCount < len(self.matchStateIdxList)) and (
                (self.matchStateIdxList[idx + baseCount] - self.matchStateIdxList[idx])
                == baseCount
            ):
                baseCount += 1
            else:
                startIdx = self.matchStateIdxList[idx]
                endIdx = self.matchStateIdxList[idx + baseCount - 1]
                self.matchStateRepeatInfoList.append(
                    RepeatSeqOutputInfo(
                        (
                            self.matchStateIdxList[idx + baseCount - 1]
                            - self.matchStateIdxList[idx]
                        ),
                        startIdx,
                        endIdx,
                        self.sequence[startIdx:endIdx],
                    )
                )
                if idx + baseCount >= len(self.matchStateIdxList):
                    break
            idx = idx + baseCount
        return self.matchStateRepeatInfoList

    def generateSeqStateSumFile(self, filePath):
        with open(filePath, "w") as f:
            f.write("".join(str(state) for state in self.seqStateSum))

    def cutRepeatSeqToFragment(self):
        """
        Using cutterA, if sequence not start from cutter
        """
        totalRepeat = pd.DataFrame(columns=["length", "startIdx", "endIdx", "seq"])
        for repeatInfo in self.matchStateRepeatInfoList:
            flag = "C"
            if repeatInfo.seq[: len(cutterB)] == cutterB:
                flag = "B"
                fragmentsLenList, fragmentsSeqList = parseSeqByCutter(
                    [repeatInfo.seq], cutter=cutterB
                )
                df = self.cauculateSeqPosition(repeatInfo, cutterB, fragmentsLenList[0])
            else:
                flag = "A"
                fragmentsLenList, fragmentsSeqList = parseSeqByCutter(
                    [repeatInfo.seq], cutter=cutterA
                )
                df = self.cauculateSeqPosition(repeatInfo, cutterA, fragmentsLenList[0])

            # For single fragment
            if len(fragmentsLenList) <= 1:
                testCutter = cutterB if flag == "A" else cutterA
                testFragmentsLenList, testFragmentsSeqList = parseSeqByCutter(
                    [repeatInfo.seq], cutter=testCutter
                )
                if len(testFragmentsLenList) > len(fragmentsLenList):
                    fragmentsLenList = testFragmentsLenList

            if (len(fragmentsLenList) > 0) and (len(fragmentsLenList[0]) > 0):
                totalRepeat = totalRepeat.append(df, ignore_index=True)
        self.repeatFrgmentDf = totalRepeat.loc[totalRepeat["length"] != 0]
        self.repeatFrgmentDf.reset_index(inplace=True, drop=True)
        return self.repeatFrgmentDf

    def cauculateSeqPosition(self, repeatInfo, cutter, fragmentsLenList):
        """
        3 Cases - Start, Middle, End
        """
        df = pd.DataFrame(columns=["length", "startIdx", "endIdx", "seq"])
        cutterLen = len(cutter)
        startIdx = repeatInfo.startIdx
        for fragmentIdx, fragmentLength in enumerate(fragmentsLenList):
            if fragmentLength > 0:
                start = (
                    startIdx
                    + sum(fragmentsLenList[:fragmentIdx])
                    + cutterLen * (fragmentIdx - 1)
                )
                end = (
                    startIdx
                    + sum(fragmentsLenList[: fragmentIdx + 1])
                    + cutterLen * (fragmentIdx + 1)
                )
                seq = self.sequence[start:end]
                # last frgment case
                if fragmentIdx == len(fragmentsLenList) - 1:
                    seq = self.sequence[start : repeatInfo.endIdx]
                    end = start + len(seq)

                df = df.append(
                    {
                        "length": len(seq),
                        "startIdx": start,
                        "endIdx": end,
                        "seq": seq,
                    },
                    ignore_index=True,
                )
        return df

    def fragmentGroupbyLen(self):
        matchDfGroupByLen = self.repeatFrgmentDf.groupby(by=["length"], sort=True)
        seqCountInLengthGroup = self.repeatFrgmentDf.groupby(
            by=["length"], as_index=False
        ).agg({"seq": "count"})

        singleRepeatFragments = seqCountInLengthGroup[seqCountInLengthGroup["seq"] == 1]
        fragmentCount = seqCountInLengthGroup["seq"].sum()

        with open(
            f"../outputFile/seqRepeatPosition/multiple_cutter_{cutterA}_{cutterB}.txt",
            "w",
        ) as f:
            fragmentInfo = f"Frgment Information - fragmentCount:{fragmentCount} \t lengthCount:{len(seqCountInLengthGroup)}\n"
            singleFragmentInfo = f"Single Fragment - count: {len(singleRepeatFragments)}, {singleRepeatFragments['length'].values}\n\n"
            f.writelines([fragmentInfo, singleFragmentInfo])
            for length in seqCountInLengthGroup["length"].values:
                f.write(f"{length}:\n")
                for i in matchDfGroupByLen.get_group(length).index:
                    f.write(
                        f"({ self.repeatFrgmentDf.iloc[i]['startIdx']}, {self.repeatFrgmentDf.iloc[i]['endIdx']})\n{ self.repeatFrgmentDf.iloc[i]['seq']}\n"
                    )
                f.write(f"\n\n")
        return 0