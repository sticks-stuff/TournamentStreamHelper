from qtpy.QtGui import *
from qtpy.QtWidgets import *
from qtpy.QtCore import *
from qtpy import uic
import json
from .Helpers.TSHCountryHelper import TSHCountryHelper
from .Helpers.TSHDirHelper import TSHResolve
from .StateManager import StateManager
from .TSHGameAssetManager import TSHGameAssetManager
from .TSHPlayerDB import TSHPlayerDB
from .TSHTournamentDataProvider import TSHTournamentDataProvider
from .TSHPlayerListSlotWidget import TSHPlayerListSlotWidget
from .TSHBracketView import TSHBracketView
from .TSHPlayerList import TSHPlayerList
from .TSHBracket import *
from .TSHHotkeys import TSHHotkeys
import traceback
from loguru import logger

# Checks if a number is power of 2


def is_power_of_two(n):
    return (n != 0) and (n & (n-1) == 0)


class TSHBracketWidgetSignals(QObject):
    UpdateData = Signal(object)


class TSHBracketWidget(QDockWidget):
    instance: "TSHBracketWidget" = None
    def __init__(self, *args):
        with StateManager.SaveBlock():
            super().__init__(*args)
            self.SetupUi()

        TSHBracketWidget.instance = self

    def SetupUi(self):
        uic.loadUi(TSHResolve("src/layout/TSHBracket.ui"), self)

        StateManager.Set("bracket", {})

        # Guards against UpdatePhaseGroup being re-entered while it pumps the
        # event loop; see UpdatePhaseGroup.
        self.updatingPhaseGroup = False
        self.pendingPhaseGroupData = None
        self.progressionsInLabels = []
        self.progressionsOutLabels = []
        self.phaseGroupSets = {}

        TSHTournamentDataProvider.instance.signals.tournament_phases_updated.connect(
            self.UpdatePhases)
        TSHTournamentDataProvider.instance.signals.tournament_phasegroup_updated.connect(
            self.UpdatePhaseGroup)

        self.signals = TSHBracketWidgetSignals()

        self.bracket = Bracket(8, 0)

        self.setFloating(True)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)

        self.mainLayout = self.findChild(QWidget, "bracket")
        self.mainLayout.setLayout(QVBoxLayout())

        self.setFloating(True)
        self.setWindowFlags(Qt.WindowType.Window)

        outerLayout: QWidget = self.findChild(QWidget, "bracket")
        self.playerList = TSHPlayerList(base="bracket.players")

        list: QWidget = self.findChild(QWidget, "listContainer")

        # Add player list settings on the top
        row = QWidget()
        row.setLayout(QHBoxLayout())
        list.layout().addWidget(row)

        col = QWidget()
        col.setLayout(QVBoxLayout())

        self.slotNumber = QSpinBox()
        self.slotNumber.setMinimum(2)
        col.layout().addWidget(QLabel(QApplication.translate("app", "Number of slots")))
        col.layout().addWidget(self.slotNumber)
        self.slotNumber.valueChanged.connect(lambda val: [
            self.playerList.SetSlotNumber(val),
            self.RebuildBracket(val),
        ])
        row.layout().addWidget(col)

        col = QWidget()
        col.setLayout(QVBoxLayout())
        self.playerPerTeam = QSpinBox()
        col.layout().addWidget(QLabel(QApplication.translate("app", "Players per slot")))
        col.layout().addWidget(self.playerPerTeam)
        self.playerPerTeam.valueChanged.connect(
            lambda val: self.playerList.SetPlayersPerTeam(val))
        row.layout().addWidget(col)

        col = QWidget()
        col.setLayout(QVBoxLayout())
        self.charNumber = QSpinBox()
        col.layout().addWidget(QLabel(QApplication.translate("app", "Characters per player")))
        col.layout().addWidget(self.charNumber)
        self.charNumber.valueChanged.connect(
            self.playerList.SetCharactersPerPlayer)
        row.layout().addWidget(col)

        list.layout().addWidget(self.playerList)

        self.bracketView = TSHBracketView(self.bracket, self.playerList, self)
        outerLayout.layout().addWidget(self.bracketView)

        self.phaseSelection: QComboBox = self.findChild(
            QComboBox, "phaseSelection")
        self.phaseSelection.currentIndexChanged.connect(self.UpdatePhaseGroups)

        self.phaseGroupSelection: QComboBox = self.findChild(
            QComboBox, "phaseGroupSelection")
        self.phaseGroupSelection.currentIndexChanged.connect(
            self.PhaseGroupChanged)

        self.btRefreshPhase: QPushButton = self.findChild(
            QPushButton, "btRefreshPhase")
        updateIcon = QImage("./assets/icons/undo.svg").scaled(24, 24)
        self.btRefreshPhase.setIcon(QIcon(QPixmap.fromImage(updateIcon)))
        self.btRefreshPhase.clicked.connect(lambda: [
            TSHTournamentDataProvider.instance.GetTournamentPhases()
        ])

        self.btRefreshPhaseGroup: QPushButton = self.findChild(
            QPushButton, "btRefreshPhaseGroup")
        updateIcon = QImage("./assets/icons/undo.svg").scaled(24, 24)
        self.btRefreshPhaseGroup.setIcon(QIcon(QPixmap.fromImage(updateIcon)))
        self.btRefreshPhaseGroup.clicked.connect(self.PhaseGroupChanged)
        TSHHotkeys.signals.refresh_phase_group.connect(self.PhaseGroupChanged)

        self.progressionsIn: QSpinBox = self.findChild(
            QSpinBox, "progressionsIn")
        self.progressionsIn.valueChanged.connect(lambda val: [
            self.bracketView.SetBracket(
                self.bracket,
                progressionsIn=self.progressionsIn.value(),
                progressionsOut=self.progressionsOut.value(),
                winnersOnlyProgressions=self.winnersOnly.isChecked(),
                customSeeding=self.bracket.customSeeding
            ),
            self.bracketView.Update()
        ])
        StateManager.Set("bracket.bracket.progressionsIn", 0)

        self.winnersOnly: QCheckBox = self.findChild(QCheckBox, "winnersOnly")
        self.winnersOnly.toggled.connect(lambda newVal: [
            self.bracketView.SetBracket(
                self.bracket,
                progressionsIn=self.progressionsIn.value(),
                progressionsOut=self.progressionsOut.value(),
                winnersOnlyProgressions=self.winnersOnly.isChecked(),
                customSeeding=self.bracket.customSeeding
            ),
            self.bracketView.Update()
        ])
        StateManager.Set("bracket.bracket.winnersOnly", True)

        self.progressionsOut: QSpinBox = self.findChild(
            QSpinBox, "progressionsOut")
        self.progressionsOut.valueChanged.connect(lambda val: [
            self.bracketView.SetBracket(
                self.bracket,
                progressionsIn=self.progressionsIn.value(),
                progressionsOut=self.progressionsOut.value(),
                winnersOnlyProgressions=self.winnersOnly.isChecked(),
                customSeeding=self.bracket.customSeeding
            ),
            self.bracketView.Update()
        ])
        StateManager.Set("bracket.bracket.progressionsOut", 0)

        self.limitExport: QCheckBox = self.findChild(QCheckBox, "limitExport")
        self.limitExport.stateChanged.connect(lambda newVal: [
            self.bracketView.SetBracket(
                self.bracket,
                progressionsIn=self.progressionsIn.value(),
                progressionsOut=self.progressionsOut.value(),
                winnersOnlyProgressions=self.winnersOnly.isChecked(),
                customSeeding=self.bracket.customSeeding
            ),
            self.bracketView.Update()
        ])
        TSHHotkeys.signals.limit_export.connect(lambda: self.limitExport.setChecked(not self.limitExport.isChecked()))

        self.limitExportNumber: QSpinBox = self.findChild(
            QSpinBox, "limitExportNumber")
        self.limitExportNumber.valueChanged.connect(lambda val: [
            self.bracketView.SetBracket(
                self.bracket,
                progressionsIn=self.progressionsIn.value(),
                progressionsOut=self.progressionsOut.value(),
                winnersOnlyProgressions=self.winnersOnly.isChecked(),
                customSeeding=self.bracket.customSeeding
            ),
            self.bracketView.Update()
        ])

        self.playerList.signals.DataChanged.connect(self.bracketView.Update)

        self.slotNumber.setValue(8)
        self.playerPerTeam.setValue(1)
        self.charNumber.setValue(1)

        self.splitter = self.findChild(QSplitter, "splitter")
        self.splitter.setSizes([1, 1])

        self.bracketView.Update()

        TSHGameAssetManager.instance.signals.onLoad.connect(
            self.SetDefaultsFromAssets
        )

    def UpdatePhases(self, phases):
        logger.info("Phases: " + str(phases))
        self.phaseSelection.clear()
        self.phaseSelection.addItem("", {})

        for phase in phases:
            self.phaseSelection.addItem(phase.get("name"), phase)

    def UpdatePhaseGroups(self):
        try:
            selectedGroup = self.phaseSelection.currentData()
            StateManager.Set("bracket.phase", selectedGroup.get("name", ""))
        except:
            StateManager.Set("bracket.phase", "")

        self.phaseGroupSelection.clear()

        if self.phaseSelection.currentData() != None:
            logger.info(
                str(self.phaseSelection.currentData().get("groups", [])))
            for phaseGroup in self.phaseSelection.currentData().get("groups", []):
                self.phaseGroupSelection.addItem(
                    phaseGroup.get("name"), phaseGroup)

                # Let's only allow double elimination for now
                if phaseGroup.get("bracketType") != "DOUBLE_ELIMINATION":
                    itemModel: QStandardItemModel = self.phaseGroupSelection.model()
                    item = itemModel.item(itemModel.rowCount()-1)
                    item.setEnabled(False)

    def PhaseGroupChanged(self):
        try:
            # Do not export phaseGroup name if there's only one phaseGroup
            if len(self.phaseSelection.currentData().get("groups", [])) > 1:
                selectedGroup = self.phaseGroupSelection.currentData()
                StateManager.Set("bracket.phaseGroup",
                                 selectedGroup.get("name"))
            else:
                StateManager.Set("bracket.phaseGroup", "")
        except:
            StateManager.Set("bracket.phaseGroup", "")

        if self.phaseGroupSelection.currentData() != None:
            TSHTournamentDataProvider.instance.GetTournamentPhaseGroup(
                self.phaseGroupSelection.currentData().get("id"))

    def RebuildBracket(self, playerNumber, seedMap=None, customSeeding=False, phaseGroupSets=None):
        self.bracket = Bracket(playerNumber, self.progressionsIn.value(
        ), seedMap, self.winnersOnly.isChecked(), progressionsOut=self.progressionsOut.value())
        self.bracket.progressionsInLabels = getattr(
            self, "progressionsInLabels", [])
        self.bracket.progressionsOutLabels = getattr(
            self, "progressionsOutLabels", [])

        if phaseGroupSets is not None:
            self.bracket.ImportPhaseGroupSets(phaseGroupSets)

        self.bracketView.SetBracket(
            self.bracket,
            progressionsIn=self.progressionsIn.value(),
            progressionsOut=self.progressionsOut.value(),
            winnersOnlyProgressions=self.winnersOnly.isChecked(),
            customSeeding=customSeeding
        )

        if phaseGroupSets is None and self.progressionsIn.value() > 0:
            for _set in self.bracket.rounds["1"]:
                _set.score[0] = -1
                _set.score[1] = -1
                _set.finished = False

        self.AssignProgressionsToSets()
        self.bracketView.Update()

    def UpdatePhaseGroup(self, phaseGroupData):
        # This method pumps the event loop (processEvents) while it runs, so a
        # second phase group payload can be delivered right in the middle of it.
        # Re-entering would unbalance the DataChanged connection and the save
        # block, so newer data is queued and applied after the current run.
        if self.updatingPhaseGroup:
            self.pendingPhaseGroupData = phaseGroupData
            return

        while True:
            self.updatingPhaseGroup = True

            try:
                with StateManager.SaveBlock():
                    self.ApplyPhaseGroup(phaseGroupData)
            finally:
                self.updatingPhaseGroup = False

            if self.pendingPhaseGroupData is None:
                break

            phaseGroupData = self.pendingPhaseGroupData
            self.pendingPhaseGroupData = None

    def ApplyPhaseGroup(self, phaseGroupData):
        try:
            self.playerList.signals.DataChanged.disconnect(
                self.bracketView.Update)
            reconnectDataChanged = True
        except TypeError:
            # Nothing was connected; don't reconnect something we didn't unhook.
            reconnectDataChanged = False

        try:
            # logger.info("Phase Group Data: " + str(phaseGroupData))

            entrants = phaseGroupData.get("entrants") or []
            sets = phaseGroupData.get("sets") or {}
            hasSetTopology = any(
                setData.get("id") is not None and setData.get("slots")
                for roundSets in sets.values()
                for setData in roundSets
            )

            # A partial fetch (e.g. one of the paginated StartGG requests
            # coming back empty/erroring) leaves entrants and sets out of
            # sync. Building the bracket from a mismatched pair crashes with
            # an IndexError once real set data is dropped into a bracket
            # sized for the wrong number of entrants, so bail out instead.
            if not entrants and sets:
                logger.warning(
                    "Phase group fetch looks partial (no entrants but sets present); skipping bracket rebuild")
                return

            self.progressionsInLabels = phaseGroupData.get("progressionsIn") or []
            self.progressionsOutLabels = phaseGroupData.get("progressionsOut") or []
            self.phaseGroupSets = phaseGroupData.get("sets") or {}

            if phaseGroupData.get("progressionsIn", {}) != None:
                self.progressionsIn.setValue(
                    len(phaseGroupData.get("progressionsIn", {})))
            else:
                self.progressionsIn.setValue(0)

            if phaseGroupData.get("progressionsOut", {}) != None:
                self.progressionsOut.setValue(
                    len(phaseGroupData.get("progressionsOut", {})))
            else:
                self.progressionsOut.setValue(0)

            if phaseGroupData.get("winnersOnlyProgressions", False) != None:
                self.winnersOnly.setChecked(
                    phaseGroupData.get("winnersOnlyProgressions", False))
            else:
                self.winnersOnly.setChecked(False)

            self.bracket.customSeeding = phaseGroupData.get(
                "customSeeding", False)

            # Make sure progressions are exported
            QGuiApplication.processEvents()

            self.playerList.LoadFromStandings(entrants)

            # Wait for the player list to update
            QGuiApplication.processEvents()

            self.slotNumber.blockSignals(True)
            self.slotNumber.setValue(len(self.playerList.slotWidgets))
            self.slotNumber.blockSignals(False)

            self.playerPerTeam.blockSignals(True)
            self.playerPerTeam.setValue(self.playerList.playersPerTeam)
            self.playerPerTeam.blockSignals(False)

            self.RebuildBracket(
                len(entrants),
                phaseGroupData.get("seedMap"),
                phaseGroupData.get("customSeeding", False),
                sets if hasSetTopology else None
            )

            if not hasSetTopology:
                for roundKey, roundSets in sets.items():
                    for setIndex, setData in enumerate(roundSets):
                        try:
                            score = setData.get("score")
                            if score[0] is None:
                                score[0] = 0
                            if score[1] is None:
                                score[1] = 0

                            bracketRound = self.bracket.rounds[str(roundKey)]
                            bracketRound[setIndex].score = score
                            bracketRound[setIndex].finished = setData.get("finished")
                        except Exception:
                            logger.error(traceback.format_exc())

            QGuiApplication.processEvents()
            self.bracket.UpdateBracket()
            self.AssignProgressionsToSets()
            self.bracketView.Update()
        except:
            logger.error(traceback.format_exc())
        finally:
            if reconnectDataChanged:
                self.playerList.signals.DataChanged.connect(
                    self.bracketView.Update)

    def AssignProgressionsToSets(self):
        self.bracket.UpdateBracket()
        for roundSets in self.bracket.rounds.values():
            for bracketSet in roundSets:
                bracketSet.progressionsInNames.clear()
                bracketSet.progressionsOutNames.clear()

        winnersCutout, losersCutout = self.bracketView.GetCutouts()
        visibleWinnerRounds = sorted(
            (int(roundKey) for roundKey in self.bracket.rounds
             if int(roundKey) > winnersCutout[0]
             and int(roundKey) < winnersCutout[1])
        )
        visibleLoserRounds = sorted(
            (int(roundKey) for roundKey in self.bracket.rounds
             if int(roundKey) < 0
             and abs(int(roundKey)) > losersCutout[0]
             and abs(int(roundKey)) < losersCutout[1]),
            key=abs,
        )

        loserEntrantNumbers = sorted({
            int(progression.get("entrantNumber"))
            for progression in self.progressionsInLabels
            if isinstance(progression, dict)
            and progression.get("entrantNumber") is not None
            and int(progression.get("destBracketSide") or 0) == 2
        })
        loserEntrantPositions = {
            entrantNumber: index
            for index, entrantNumber in enumerate(loserEntrantNumbers)
        }

        setsById = {}
        seedSetById = {}
        for roundKey, roundSets in self.phaseGroupSets.items():
            for setIndex, setData in enumerate(roundSets):
                setId = str(setData.get("id"))
                setsById[setId] = (int(roundKey), setIndex, setData)
                for slot in setData.get("slots", []):
                    if slot.get("prereqType") == "seed":
                        seedSetById[str(slot.get("prereqId"))] = setId

        def findVisibleSetForSeed(seedId, targetRounds, isLosersSide):
            currentSetId = seedSetById.get(str(seedId))
            visited = set()
            while currentSetId and currentSetId not in visited:
                visited.add(currentSetId)
                location = setsById.get(currentSetId)
                if location and location[0] in targetRounds:
                    return self.bracket.rounds[str(location[0])][location[1]]

                placement = 1
                if isLosersSide and location and location[0] > 0:
                    placement = 2

                nextSets = []
                for roundSets in self.phaseGroupSets.values():
                    for setData in roundSets:
                        if any(
                            slot.get("prereqType") == "set"
                            and str(slot.get("prereqId")) == currentSetId
                            and int(slot.get("prereqPlacement") or 0)
                            == placement
                            for slot in setData.get("slots", [])
                        ):
                            nextSets.append(setData)
                if not nextSets:
                    return None

                nextSet = nextSets[0]
                nextSetId = str(nextSet.get("id"))
                currentSetId = nextSetId
            return None

        for progression in self.progressionsInLabels:
            if not isinstance(progression, dict):
                continue
            name = progression.get("label") or progression.get(
                "placeholderName") or progression.get("name")
            entrantNumber = progression.get("entrantNumber")
            if entrantNumber is None or not name:
                continue

            isLosersSide = int(progression.get("destBracketSide") or 0) == 2
            if progression.get("destBracketSide") is None:
                isLosersSide = "loser" in str(name).casefold()
            targetRounds = visibleLoserRounds if isLosersSide else visibleWinnerRounds
            targetSet = None
            if isLosersSide and progression.get("seedId") is not None:
                targetSet = findVisibleSetForSeed(
                    progression.get("seedId"), targetRounds, isLosersSide)

            if targetSet is None and isLosersSide and targetRounds:
                if targetSet is None:
                    targetRound = targetRounds[0]
                    targetRoundSets = self.bracket.rounds[str(targetRound)]
                    loserPosition = loserEntrantPositions.get(int(entrantNumber))
                    targetSetIndex = (
                        loserPosition * len(targetRoundSets) // len(loserEntrantNumbers)
                        if loserPosition is not None and loserEntrantNumbers
                        else None
                    )
                    if targetSetIndex is not None and targetSetIndex < len(targetRoundSets):
                        targetSet = targetRoundSets[targetSetIndex]
            elif targetSet is None:
                for roundNum in targetRounds:
                    targetSet = next((
                        bracketSet for bracketSet in self.bracket.rounds[str(roundNum)]
                        if str(entrantNumber) in {str(playerId) for playerId in bracketSet.playerIds}
                    ), None)
                    if targetSet:
                        break

                if targetSet is None:
                    initialRound = self.bracket.rounds.get("1", [])
                    initialSetIndex = next((
                        index for index, bracketSet in enumerate(initialRound)
                        if str(entrantNumber) in {str(playerId) for playerId in bracketSet.playerIds}
                    ), None)
                    if initialSetIndex is not None and targetRounds:
                        targetRound = targetRounds[0]
                        targetSetIndex = initialSetIndex // (2 ** (targetRound - 1))
                        targetRoundSets = self.bracket.rounds[str(targetRound)]
                        if targetSetIndex < len(targetRoundSets):
                            targetSet = targetRoundSets[targetSetIndex]
                    elif initialSetIndex is not None:
                        targetSet = initialRound[initialSetIndex]

            if targetSet:
                targetSet.progressionsInNames.append(str(name))

        def progressionGroupKey(progression):
            return progression.get("linkId") or (
                progression.get("phaseId"),
                progression.get("originLosses"),
                progression.get("originPlacement"),
                progression.get("name"),
            )

        outputCounts = {}
        for progression in self.progressionsOutLabels:
            if isinstance(progression, dict):
                key = progressionGroupKey(progression)
                outputCounts[key] = outputCounts.get(key, 0) + 1

        outputIndexes = {}
        for progression in self.progressionsOutLabels:
            if not isinstance(progression, dict):
                continue
            name = (
                progression.get("label")
                or progression.get("name")
                or progression.get("phaseName")
            )
            if not name:
                continue

            isLosersSide = int(progression.get("originLosses", 0) or 0) > 0
            targetRounds = visibleLoserRounds if isLosersSide else visibleWinnerRounds
            if not targetRounds:
                continue

            targetRound = targetRounds[-1]

            targetSets = self.bracket.rounds[str(targetRound)]
            progressionKey = progressionGroupKey(progression)
            targetSetIndex = outputIndexes.get(progressionKey, 0)
            outputIndexes[progressionKey] = targetSetIndex + 1
            groupSize = outputCounts.get(progressionKey, 1)
            if targetSets:
                targetSetIndex = min(
                    targetSetIndex * len(targetSets) // groupSize,
                    len(targetSets) - 1,
                )
                targetSet = targetSets[targetSetIndex]
            else:
                targetSet = None
            if targetSet:
                targetSet.progressionsOutNames.append(str(name))

    def SetDefaultsFromAssets(self):
        if StateManager.Get(f'game.defaults'):
            players, characters = StateManager.Get(f'game.defaults.players_per_team', 1), StateManager.Get(f'game.defaults.characters_per_player', 1)
        else:
            players, characters = 1, 1
        self.playerPerTeam.setValue(players)
        self.charNumber.setValue(characters)
