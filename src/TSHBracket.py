import math
from .Helpers.TSHLocaleHelper import TSHLocaleHelper
from loguru import logger
import traceback


class BracketSet():
    BYE = -1
    PENDING = -2

    def __init__(self, bracket: "Bracket", pos) -> None:
        self.bracket: Bracket = bracket
        self.playerIds = [BracketSet.BYE, BracketSet.BYE]
        self.score = [0, 0]
        self.winNext: "BracketSet" = None
        self.winNextSlot: int = 0
        self.loseNext: "BracketSet" = None
        self.loseNextSlot: int = 0
        self.pos = pos
        self.finished = False

# Bracket always has a power of 2 number of players
# if there are less than that, we round up and add
# 'bye's as the lower seeded players


def next_power_of_2(x):
    return 1 if x == 0 else 2**math.ceil(math.log2(x))

# Seeding order logic


def seeding(numPlayers):
    rounds = math.log(numPlayers)/math.log(2)-1
    pls = [1, 2]
    for i in range(int(rounds)):
        pls = nextLayer(pls)
    return pls

# Checks if a number is power of 2


def is_power_of_two(n):
    return (n != 0) and (n & (n-1) == 0)


def nextLayer(pls):
    out = []
    length = len(pls)*2+1

    for d in pls:
        out.append(d)
        out.append(length-d)
    return out


class Bracket():
    def __init__(self, playerNumber, progressionsIn, seedMap=None, winnersOnlyProgressions=False, customSeeding=False, progressionsOut=0) -> None:
        self.originalPlayerNumber = playerNumber
        self.playerNumber = next_power_of_2(playerNumber)

        self.progressionsIn = progressionsIn
        self.progressionsOut = progressionsOut
        self.hasImportedTopology = False
        self.importedUpdateOrder = []

        if seedMap:
            if len(seedMap) < self.playerNumber:
                for i in range(len(seedMap)+1, self.playerNumber+1):
                    seedMap.append(-1)
            seeds = seedMap
        else:
            seeds = seeding(self.playerNumber)

        self.seedMap = seeds

        self.winnersOnlyProgressions = winnersOnlyProgressions

        self.customSeeding = customSeeding

        if progressionsIn > 0 and -1 in self.seedMap:
            self.winnersOnlyProgressions = True

        self.rounds = {}

        for i in range(len(seeds)):
            if seeds[i] > self.originalPlayerNumber:
                seeds[i] = -1

        # Create winners
        self.rounds["1"] = []
        for i in range(self.playerNumber):
            if i % 2 == 0:
                _set = BracketSet(self, [1, len(self.rounds["1"])])
                _set.playerIds[0] = seeds[i]
                _set.playerIds[1] = seeds[i+1]
                self.rounds["1"].append(_set)

        # Create losers
        self.rounds["-1"] = []
        self.rounds["-2"] = []
        for i in range(int(self.playerNumber/2)):
            self.rounds["-1"].append(BracketSet(self,
                                     [-1, int(len(self.rounds["-1"])/2)]))
            self.rounds["-2"].append(BracketSet(self,
                                     [-1, int(len(self.rounds["-2"])/2)]))

        # Fill with -1
        for round in ["-1", "-2"]:
            for _set in self.rounds[round]:
                _set.score = [-1, -1]
                _set.finished = True

        # Expand winners
        subBracket = []
        i = self.playerNumber/2

        while i > 1:
            i = math.floor(i/2)
            round = [BracketSet(self, [2+len(subBracket), i])
                     for i in range(int(i))]
            subBracket.append(round)
        subBracket.append([BracketSet(self, [2+len(subBracket), 0])])
        subBracket.append([BracketSet(self, [2+len(subBracket), 0])])

        for r, round in enumerate(subBracket):
            self.rounds[str(2+r)] = round

        # Expand losers
        subBracket = []
        i = self.playerNumber/2

        while i > 1:
            i = math.floor(i/2)
            for j in range(2):
                round = [BracketSet(self, [-1-len(subBracket), i])
                         for i in range(math.floor(i))]
                subBracket.append(round)

        for r, round in enumerate(subBracket):
            self.rounds[str(-3-r)] = round

        # Connect sets
        for k, round in self.rounds.items():
            roundNum = int(k)

            if roundNum > 0:
                for j, _set in enumerate(round):
                    try:
                        _set.winNext = self.rounds[str(
                            roundNum+1)][math.floor(j/2)]
                        targetIdW = j % 2
                        if int(k) < 0 and abs(int(k)) % 2 == 1:
                            targetIdW = 1
                        _set.winNextSlot = targetIdW
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except:
                        logger.error(traceback.format_exc())
                    try:
                        if abs(roundNum) % 4 == 0:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(int(len(round)/2)+j) % len(round)]
                        elif abs(roundNum) % 4 == 1:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][j]
                        elif abs(roundNum) % 4 == 2:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(-1-j) % len(round)]
                        elif abs(roundNum) % 4 == 3:
                            _set.loseNext = self.rounds[str(-int(2*(roundNum)))][(int(len(round)/2)-1-j) % len(round)]

                        targetIdL = 0

                        if roundNum == 1:
                            targetIdL = j % 2

                        _set.loseNextSlot = targetIdL
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except:
                        logger.error(traceback.format_exc())
            else:
                for j, _set in enumerate(round):
                    try:
                        if abs(roundNum) % 2 == 0:
                            _set.winNext = self.rounds[str(
                                roundNum-1)][math.floor(j/2)]
                        else:
                            _set.winNext = self.rounds[str(roundNum-1)][j]
                        targetIdW = j % 2
                        if int(k) < 0 and abs(int(k)) % 2 == 1:
                            targetIdW = 1
                        _set.winNextSlot = targetIdW
                    except KeyError as e:
                        logger.warning(f"Bracket KeyError: {e}")
                    except Exception as e:
                        logger.error(e)

        # Connect losers to winners for grand finals
        lastLosers = min([int(r) for r in self.rounds.keys()])
        gfsRound = max([int(r) for r in self.rounds.keys()]) - 1
        self.rounds[str(lastLosers)][0].winNext = self.rounds[str(gfsRound)][0]
        self.rounds[str(lastLosers)][0].winNextSlot = 1

        # Connect grand finals to reset
        gfsResetRound = max([int(r) for r in self.rounds.keys()])
        gfsRound = gfsResetRound - 1
        self.rounds[str(gfsRound)][0].winNext = self.rounds[str(
            gfsResetRound)][0]
        self.rounds[str(gfsRound)][0].winNextSlot = 0
        self.rounds[str(gfsRound)][0].loseNext = self.rounds[str(
            gfsResetRound)][0]
        self.rounds[str(gfsRound)][0].loseNextSlot = 1

    def IsBye(self, playerId):
        if playerId == -1 or playerId > self.originalPlayerNumber:
            return True
        return False

    def GetLeadingLosersByeRounds(self):
        if not self.hasImportedTopology:
            return 0

        losersRounds = sorted(
            abs(int(roundKey))
            for roundKey in self.rounds
            if int(roundKey) < 0
        )
        skippedRounds = 0

        for expectedRound, roundNumber in enumerate(losersRounds, start=1):
            if roundNumber != expectedRound:
                break

            roundSets = self.rounds[str(-roundNumber)]
            if not roundSets or not all(
                any(self.IsBye(playerId) for playerId in bracketSet.playerIds)
                for bracketSet in roundSets
            ):
                break

            skippedRounds += 1

        return skippedRounds

    def ImportPhaseGroupSets(self, phaseGroupSets):
        importedRounds = {}
        setsById = {}
        prerequisites = []

        for roundKey in sorted(phaseGroupSets, key=lambda key: (int(key) < 0, abs(int(key)))):
            roundNumber = int(roundKey)
            importedRounds[str(roundNumber)] = []

            for setData in phaseGroupSets[roundKey]:
                bracketSet = BracketSet(self, [roundNumber, len(importedRounds[str(roundNumber)])])
                bracketSet.id = str(setData.get("id"))
                bracketSet.score = [
                    0 if score is None else score
                    for score in setData.get("score", [0, 0])
                ]
                bracketSet.finished = setData.get("finished", False)

                slots = setData.get("slots") or []
                for slotIndex in range(2):
                    slot = slots[slotIndex] if slotIndex < len(slots) else {}
                    playerId = slot.get("playerId")
                    if playerId is not None:
                        bracketSet.playerIds[slotIndex] = playerId
                    elif slot.get("prereqType") in ("bye", "seed"):
                        bracketSet.playerIds[slotIndex] = BracketSet.BYE
                    else:
                        bracketSet.playerIds[slotIndex] = BracketSet.PENDING

                    if slot.get("prereqType") == "set" and slot.get("prereqId") is not None:
                        prerequisites.append((bracketSet, slotIndex, slot))

                importedRounds[str(roundNumber)].append(bracketSet)
                if bracketSet.id not in ("None", ""):
                    setsById[bracketSet.id] = bracketSet

        for target, targetSlot, slot in prerequisites:
            source = setsById.get(str(slot.get("prereqId")))
            if source is None:
                continue

            try:
                placement = int(slot.get("prereqPlacement"))
            except (TypeError, ValueError):
                continue

            if placement == 1:
                source.winNext = target
                source.winNextSlot = targetSlot
            elif placement == 2:
                source.loseNext = target
                source.loseNextSlot = targetSlot

        allSets = [bracketSet for roundSets in importedRounds.values() for bracketSet in roundSets]
        incomingCounts = {bracketSet: 0 for bracketSet in allSets}
        for bracketSet in allSets:
            for target in (bracketSet.winNext, bracketSet.loseNext):
                if target is not None:
                    incomingCounts[target] += 1

        def sortKey(bracketSet):
            return (
                bracketSet.pos[0] < 0,
                abs(bracketSet.pos[0]),
                bracketSet.pos[1],
            )

        ready = sorted(
            (bracketSet for bracketSet, count in incomingCounts.items() if count == 0),
            key=sortKey,
        )
        self.importedUpdateOrder = []
        while ready:
            bracketSet = ready.pop(0)
            self.importedUpdateOrder.append(bracketSet)
            for target in (bracketSet.winNext, bracketSet.loseNext):
                if target is None:
                    continue
                incomingCounts[target] -= 1
                if incomingCounts[target] == 0:
                    ready.append(target)
                    ready.sort(key=sortKey)

        if len(self.importedUpdateOrder) != len(allSets):
            ordered = set(self.importedUpdateOrder)
            self.importedUpdateOrder.extend(sorted(
                (bracketSet for bracketSet in allSets if bracketSet not in ordered),
                key=sortKey,
            ))

        self.rounds = importedRounds
        self.hasImportedTopology = True

    def UpdateBracket(self):
        if self.hasImportedTopology:
            orderedSets = [(str(bracketSet.pos[0]), bracketSet) for bracketSet in self.importedUpdateOrder]
        else:
            orderedSets = [
                (roundKey, bracketSet)
                for roundKey, roundSets in sorted(self.rounds.items(), key=lambda item: (int(item[0]) < 0, abs(int(item[0]))))
                for bracketSet in roundSets
            ]

        for roundKey, _set in orderedSets:
            # When we have progressions in, force first (hidden) sets to double DQs
            # If we have a non-power of 2 number of progressions in, we do it for 2 rounds
            if not self.hasImportedTopology and self.progressionsIn > 0 and not self.winnersOnlyProgressions:
                if int(roundKey) == 1:
                    _set.score = [-1, -1]
                    _set.finished = True

                if int(roundKey) == 2 and not is_power_of_two(self.progressionsIn) and not self.customSeeding:
                    _set.score = [-1, -1]
                    _set.finished = True

            if not (_set.winNext or _set.loseNext):
                continue

            if (self.IsBye(_set.playerIds[0]) and self.IsBye(_set.playerIds[1])) or \
                    (not self.IsBye(_set.playerIds[0]) and self.IsBye(_set.playerIds[1])):
                won, lost = 0, 1
            elif self.IsBye(_set.playerIds[0]) and not self.IsBye(_set.playerIds[1]):
                won, lost = 1, 0
            elif _set.score[0] == -1 and _set.score[1] == -1:
                won = 0 if _set.playerIds[0] < _set.playerIds[1] else 1
                lost = 0 if won == 1 else 1
            elif not _set.finished:
                if _set.winNext:
                    _set.winNext.playerIds[_set.winNextSlot] = BracketSet.PENDING
                if _set.loseNext:
                    _set.loseNext.playerIds[_set.loseNextSlot] = BracketSet.PENDING
                continue
            elif _set.score[0] > _set.score[1]:
                won, lost = 0, 1
            elif _set.score[0] < _set.score[1]:
                won, lost = 1, 0
            else:
                if _set.winNext:
                    _set.winNext.playerIds[_set.winNextSlot] = BracketSet.PENDING
                if _set.loseNext:
                    _set.loseNext.playerIds[_set.loseNextSlot] = BracketSet.PENDING
                continue

            if _set.winNext:
                _set.winNext.playerIds[_set.winNextSlot] = _set.playerIds[won]
            if _set.loseNext:
                _set.loseNext.playerIds[_set.loseNextSlot] = _set.playerIds[lost]

        # Clear scores when no players in set
        # for k, round in sorted(self.rounds.items(), key=lambda x: (int(x[0]) < 0, abs(int(x[0])))):
        #     for j, _set in enumerate(round):
        #         if _set.playerIds[0] == -2 or _set.playerIds[1] == -2:
        #             _set.score[0] = 0
        #             _set.score[1] = 0

    # Get round names
    def GetRoundName(self, round: str, winnersCutout=[0, 0], losersCutout=[0, 0]):
        roundNumber = int(round)

        gfsRound = max([int(r) for r in self.rounds.keys()]) - 1
        lastLosers = min([int(r) for r in self.rounds.keys()])

        if self.progressionsOut <= 0:
            if roundNumber > 0:
                if roundNumber == gfsRound:
                    return TSHLocaleHelper.matchNames.get("grand_final")
                if roundNumber == gfsRound + 1:
                    return TSHLocaleHelper.matchNames.get("grand_final_reset")
                if roundNumber == gfsRound - 1:
                    return TSHLocaleHelper.matchNames.get("winners_final")
                if roundNumber == gfsRound - 2:
                    return TSHLocaleHelper.matchNames.get("winners_semi_final")
                if roundNumber == gfsRound - 3:
                    return TSHLocaleHelper.matchNames.get("winners_quarter_final")
            else:
                if roundNumber == lastLosers:
                    return TSHLocaleHelper.matchNames.get("losers_final")
                if roundNumber == lastLosers + 1:
                    return TSHLocaleHelper.matchNames.get("losers_semi_final")
                if roundNumber == lastLosers + 2:
                    return TSHLocaleHelper.matchNames.get("losers_quarter_final")
                if roundNumber == lastLosers + 3:
                    return TSHLocaleHelper.matchNames.get("losers_top8")

        if roundNumber > 0:
            roundNumber -= winnersCutout[0]
            return TSHLocaleHelper.matchNames.get("winners_round").format(abs(roundNumber))
        if roundNumber < 0:
            roundNumber += losersCutout[0]
            return TSHLocaleHelper.matchNames.get("losers_round").format(abs(roundNumber))

    @staticmethod
    def GetTopN(round_number: int, bracket_size: int):
        print("Input:", round_number, bracket_size)

        if round_number >= 0:
            return bracket_size // (2 ** (round_number-1))
        else:
            return math.ceil(bracket_size / (2 ** (abs(round_number-1)/2)))
