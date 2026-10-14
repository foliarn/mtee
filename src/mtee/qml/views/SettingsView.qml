import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// Settings editor tab, as in VS Code: one tab of the editor whose pages are chosen in the
// tab strip below the heading (General, Library, Playback, Analysis, Keyboard shortcuts,
// Data & privacy, About). The app's sidebar is not part of this page. Every setting is wired
// to a real model; the Data & privacy actions ask for confirmation first.
Rectangle {
    id: settings

    objectName: "settingsView"
    required property var workspace
    property int groupIndex: 0
    property int bottomInset: 0
    // The page shown for this group. A method call is not a tracked binding, so the value is
    // read again whenever the workspace layout changes (a page was chosen).
    property string page: workspace.settingsPageForGroup(groupIndex)
    readonly property var analysis: workspace.analysisSettings
    readonly property var playback: workspace.playbackSettings
    readonly property var categories: [
        { "key": "general", "label": "General" },
        { "key": "library", "label": "Library" },
        { "key": "playback", "label": "Playback" },
        { "key": "analysis", "label": "Analysis" },
        { "key": "shortcuts", "label": "Keyboard shortcuts" },
        { "key": "privacy", "label": "Data & privacy" },
        { "key": "about", "label": "About" }
    ]
    readonly property bool privacyAvailable: typeof dataPrivacy !== "undefined"
    readonly property bool rulesAvailable: typeof artistRules !== "undefined"
    readonly property bool historyAvailable: typeof workspace.playerModel !== "undefined"
        && typeof workspace.playerModel.clearHistory === "function"
    readonly property int historyCount: historyAvailable ? workspace.playerModel.history.length : 0
    readonly property bool restorePending: privacyAvailable && Object.keys(dataPrivacy.pendingRestore).length > 0
    readonly property string restoreFileName: restorePending
        ? String(dataPrivacy.pendingRestore.sourceName) : ""
    readonly property bool privacyBusy: privacyAvailable && dataPrivacy.busy

    // Confirmation dialog currently open: "" (none), "clear-history", "reset-statistics"
    // or "restore". The backup chosen for a restore is kept until it is confirmed.
    property string dialog: ""
    property url backupSource
    property string notice: ""

    color: Theme.editor

    Shortcut {
        sequence: "Esc"
        enabled: settings.dialog.length > 0
        onActivated: settings.dialog = ""
    }

    Connections {
        target: settings.workspace
        function onLayoutChanged() { settings.page = settings.workspace.settingsPageForGroup(settings.groupIndex) }
    }

    Connections {
        target: settings.privacyAvailable ? dataPrivacy : null
        ignoreUnknownSignals: true
        function onFinished(message) { settings.notice = message }
        function onNoticeRaised(message) { settings.notice = message }
    }

    Flickable {
        id: settingsFlick
        anchors.fill: parent
        contentHeight: content.implicitHeight + 48 + settings.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: content
            x: 24
            width: Math.min(720, settings.width - 48)
            spacing: 8

            Item { width: 1; height: 30 }

            SectionLabel { text: "Preferences" }

            Text {
                text: "Settings"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeHeading
                font.weight: Font.Bold
            }

            // The pages, as tabs of this editor tab. The strip scrolls sideways when the window is narrow.
            Flickable {
                id: tabFlick
                objectName: "settingsTabs"
                width: content.width
                height: Theme.tabHeight
                contentWidth: tabRow.width
                contentHeight: Theme.tabHeight
                flickableDirection: Flickable.HorizontalFlick
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Row {
                    id: tabRow
                    height: Theme.tabHeight

                    Repeater {
                        model: settings.categories

                        delegate: Item {
                            id: tabItem
                            required property var modelData
                            readonly property bool current: settings.page === modelData.key

                            objectName: "settingsTab_" + modelData.key
                            width: tabLabel.implicitWidth + 24
                            height: Theme.tabHeight

                            Text {
                                id: tabLabel
                                anchors.centerIn: parent
                                text: tabItem.modelData.label.toUpperCase()
                                color: tabItem.current || tabMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeCaption
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1.1
                            }

                            Rectangle {
                                visible: tabItem.current
                                anchors.bottom: parent.bottom
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: tabLabel.implicitWidth
                                height: 2
                                color: Theme.primary
                            }

                            MouseArea {
                                id: tabMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: settings.workspace.setSettingsPageForGroup(settings.groupIndex, tabItem.modelData.key)
                            }
                        }
                    }
                }
            }

            // General: the only setting left here is the preview-tab behaviour.
            Column {
                id: generalPage
                objectName: "generalSettings"
                width: content.width
                visible: settings.page === "general"
                spacing: 8

                Group { title: "Tabs"; visible: typeof settings.workspace.setPreviewTabs === "function" }

                ToggleRow {
                    objectName: "previewTabsSetting"
                    visible: typeof settings.workspace.setPreviewTabs === "function"
                    label: "Open folders and playlists in preview tabs"
                    description: "Browsing reuses one italic tab instead of adding a new one each time. Double-click the tab, or sort, search or change its view, to keep it."
                    checked: settings.workspace.previewTabs === true
                    onToggled: (checked) => settings.workspace.setPreviewTabs(checked)
                }
            }

            // Library: the artist name rules chosen in the Artists view.
            Column {
                objectName: "librarySettings"
                width: content.width
                visible: settings.page === "library"
                spacing: 8

                Group { title: "Artist name rules" }

                Text {
                    width: parent.width
                    topPadding: 8
                    wrapMode: Text.WordWrap
                    visible: settings.rulesAvailable
                    text: "Decisions you made on artist names. \"This is one artist\" keeps a name whole; \"Split into separate artists\" divides it. Removing a rule brings back the automatic grouping for that name."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Text {
                    visible: !settings.rulesAvailable
                    width: parent.width
                    topPadding: 8
                    wrapMode: Text.WordWrap
                    text: "Artist name rules are not available in the demo."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Repeater {
                    model: settings.rulesAvailable ? artistRules.rules : []

                    delegate: Item {
                        id: ruleRow
                        required property var modelData
                        width: content.width
                        height: 52

                        Column {
                            anchors.left: parent.left
                            anchors.right: removeButton.left
                            anchors.rightMargin: 24
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2

                            Text {
                                width: parent.width
                                text: ruleRow.modelData.text
                                elide: Text.ElideRight
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeBody
                            }

                            Text {
                                text: ruleRow.modelData.decision
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }

                        TextButton {
                            id: removeButton
                            objectName: "removeRule_" + ruleRow.modelData.id
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            implicitHeight: 28
                            kind: "ghost"
                            text: "Remove rule"
                            tip: "The name goes back to the automatic grouping"
                            onClicked: artistRules.removeRule(ruleRow.modelData.id)
                        }

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: Theme.separator
                        }
                    }
                }

                Text {
                    visible: settings.rulesAvailable && artistRules.rules.length === 0
                    topPadding: 16
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "No rules yet. Choose \"This is one artist\" or \"Split into separate artists\" on a name in the Artists view."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Text {
                    visible: settings.rulesAvailable && artistRules.message.length > 0
                    topPadding: 12
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: settings.rulesAvailable ? artistRules.message : ""
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            // Playback: the player island and the loudness normalization (plan 116).
            Column {
                objectName: "playbackSettings"
                width: content.width
                visible: settings.page === "playback"
                spacing: 8

                Group { title: "Player" }

                ToggleRow {
                    objectName: "islandSetting"
                    label: "Show player island"
                    description: "Floating player at the bottom of the editor while a track is loaded. Also in View › Player island."
                    checked: settings.workspace.islandEnabled
                    onToggled: (checked) => settings.workspace.setIslandEnabled(checked)
                }

                Group { title: "Loudness" }

                ToggleRow {
                    objectName: "normalizationSetting"
                    label: "Normalize loudness"
                    description: "Play analyzed tracks at a similar loudness, using the loudness measured by Analyze. Tracks not analyzed yet play as they are. The files are never changed."
                    checked: settings.playback.normalizationEnabled
                    onToggled: (checked) => settings.playback.setNormalizationEnabled(checked)
                }

                ChoiceRow {
                    objectName: "normalizationLevelSetting"
                    label: "Loudness target"
                    description: "Quiet -23 LUFS, Normal -14 LUFS, Loud -11 LUFS. Louder tracks are turned down. Quieter tracks are turned up by at most 12 dB, and never past a -2 dBFS peak."
                    options: [{ "value": "quiet", "label": "Quiet" }, { "value": "normal", "label": "Normal" }, { "value": "loud", "label": "Loud" }]
                    current: settings.playback.normalizationLevel
                    onChosen: (value) => settings.playback.setNormalizationLevel(value)
                }
            }

            // Analysis: unchanged controls of the analysis settings (plan 33).
            Column {
                id: analysisPage
                objectName: "analysisSettings"
                width: content.width
                visible: settings.page === "analysis"
                spacing: 8

                Text {
                    width: parent.width
                    topPadding: 12
                    text: "Tracks are analyzed only when you ask: right-click a track or a folder and choose Analyze. Results are stored permanently."
                    wrapMode: Text.WordWrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Group { title: "Key" }

                ChoiceRow {
                    objectName: "notationSetting"
                    label: "Key notation"
                    description: "How keys are written in the track list, the inspector and the player: Camelot (8A) or classic (Am)."
                    options: [{ "value": "camelot", "label": "Camelot" }, { "value": "classic", "label": "Classic" }]
                    current: settings.analysis.notation
                    onChosen: (value) => settings.analysis.setNotation(value)
                }

                Group { title: "Tempo" }

                StepperRow {
                    objectName: "bpmMinSetting"
                    label: "Lowest BPM"
                    description: "Tempos are halved or doubled to fall inside the range. The highest BPM is always at least twice the lowest."
                    value: settings.analysis.bpmMin
                    from: 40
                    to: 150
                    step: 5
                    onChosen: (value) => settings.analysis.setBpmMin(value)
                }

                StepperRow {
                    objectName: "bpmMaxSetting"
                    label: "Highest BPM"
                    description: "Narrow the range to settle half-time or double-time ambiguity, for example 90 to 180."
                    value: settings.analysis.bpmMax
                    from: 80
                    to: 300
                    step: 5
                    onChosen: (value) => settings.analysis.setBpmMax(value)
                }

                ChoiceRow {
                    objectName: "bpmDecimalsSetting"
                    label: "BPM decimals shown"
                    description: "Analyzed tempos are stored with more precision than they are shown."
                    options: [{ "value": 0, "label": "0" }, { "value": 1, "label": "1" }, { "value": 2, "label": "2" }]
                    current: settings.analysis.bpmDecimals
                    onChosen: (value) => settings.analysis.setBpmDecimals(value)
                }

                Group { title: "Processing" }

                StepperRow {
                    objectName: "parallelSetting"
                    label: "Analyses in parallel"
                    description: "Tracks analyzed at the same time. A higher number is faster but slows the rest of MTEE while a batch runs."
                    value: settings.analysis.parallelJobs
                    from: 1
                    to: 8
                    step: 1
                    onChosen: (value) => settings.analysis.setParallelJobs(value)
                }

                ToggleRow {
                    objectName: "writeTagsSetting"
                    label: "Write results into the file tags"
                    description: "After an analysis, copy BPM and key into the tags of the audio file, replacing the ones already there. This rewrites each file. Off by default."
                    checked: settings.analysis.writeTags
                    onToggled: (checked) => settings.analysis.setWriteTags(checked)
                }
            }

            // Keyboard shortcuts: read-only, the ones MTEE handles (checked in the QML sources).
            Column {
                objectName: "shortcutSettings"
                width: content.width
                visible: settings.page === "shortcuts"
                spacing: 0

                Text {
                    width: parent.width
                    topPadding: 12
                    bottomPadding: 12
                    text: "Read-only list of the shortcuts MTEE handles. Shortcuts that depend on a selection work only while that selection exists."
                    wrapMode: Text.WordWrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Repeater {
                    model: [
                        { "action": "Play or pause the loaded track", "keys": "Space" },
                        { "action": "Play the selected track", "keys": "Enter or double-click" },
                        { "action": "Move the selection up or down (Shift extends it)", "keys": "Up / Down" },
                        { "action": "Select all tracks in the list", "keys": "Ctrl+A" },
                        { "action": "Clear the selection", "keys": "Esc" },
                        { "action": "Show or hide the info panel", "keys": "Ctrl+I" },
                        { "action": "Save the tag changes in the info panel", "keys": "Ctrl+S" },
                        { "action": "Undo the last save", "keys": "Ctrl+Z" },
                        { "action": "Show the Explorer", "keys": "Ctrl+Shift+E" },
                        { "action": "Show or hide the sidebar", "keys": "Ctrl+B" },
                        { "action": "Split the editor", "keys": "Ctrl+\\" },
                        { "action": "Open Settings", "keys": "Ctrl+," },
                        { "action": "Close the active tab", "keys": "Ctrl+W" },
                        { "action": "Next or previous track", "keys": "Ctrl+Right / Ctrl+Left" },
                        { "action": "Fullscreen player", "keys": "F11 (Esc leaves it)" },
                        { "action": "Fullscreen: next or previous page", "keys": "Down / Up, PgDown / PgUp" },
                        { "action": "Move the selected files to the Recycle Bin", "keys": "Del (Explorer only)" }
                    ]

                    delegate: Item {
                        id: shortcutRow
                        required property var modelData
                        width: content.width
                        height: 36

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - keysBadge.width - 24
                            elide: Text.ElideRight
                            text: shortcutRow.modelData.action
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }

                        Rectangle {
                            id: keysBadge
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: keysText.implicitWidth + 16
                            height: 24
                            color: Theme.surface
                            border.color: Theme.separator

                            Text {
                                id: keysText
                                anchors.centerIn: parent
                                text: shortcutRow.modelData.keys
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                                font.features: { "tnum": 1 }
                            }
                        }

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: Theme.separator
                        }
                    }
                }
            }

            // Data & privacy: each destructive action asks first (plan 114).
            Column {
                objectName: "privacySettings"
                width: content.width
                visible: settings.page === "privacy"
                spacing: 8

                Group { title: "Listening history" }

                ActionRow {
                    objectName: "clearHistoryRow"
                    label: "Clear listening history"
                    description: "Empties the History panel, which keeps the last 100 listenings. Your statistics are not changed."
                    detail: settings.historyAvailable ? settings.historyCount + " of 100 entries" : ""
                    actionText: "Clear history…"
                    enabledAction: settings.historyAvailable && settings.historyCount > 0
                    onAction: settings.dialog = "clear-history"
                }

                Group { title: "Statistics" }

                ActionRow {
                    objectName: "resetStatisticsRow"
                    label: "Reset listening statistics"
                    description: "Deletes every listening event: totals, top tracks, top albums and the chart. The installation identifier is kept. This cannot be undone."
                    actionText: "Reset statistics…"
                    enabledAction: settings.privacyAvailable && !settings.privacyBusy
                    danger: true
                    onAction: settings.dialog = "reset-statistics"
                }

                Group { title: "Database" }

                ActionRow {
                    objectName: "backUpRow"
                    label: "Back up database"
                    description: "Writes a consistent copy of the library database to a file you choose, and checks it. An existing file is never overwritten."
                    actionText: "Back up…"
                    enabledAction: settings.privacyAvailable && !settings.privacyBusy
                    onAction: backupDialog.open()
                }

                ActionRow {
                    objectName: "restoreRow"
                    label: "Restore database"
                    description: "Choose a backup to restore. It is checked first and applied the next time MTEE starts; a copy of the current database is kept."
                    detail: settings.restorePending
                        ? "Restore scheduled from " + settings.restoreFileName + ". Restart MTEE to apply it."
                        : (settings.privacyAvailable ? dataPrivacy.lastRestoreMessage : "")
                    actionText: settings.restorePending ? "Cancel restore" : "Restore from backup…"
                    enabledAction: settings.privacyAvailable && !settings.privacyBusy
                    onAction: {
                        if (settings.restorePending) dataPrivacy.cancelRestore()
                        else restoreDialog.open()
                    }
                }

                Text {
                    visible: settings.notice.length > 0
                    topPadding: 16
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: settings.notice
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Text {
                    visible: !settings.privacyAvailable
                    topPadding: 16
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Data actions are not available in the demo."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            // About: the version comes from the application (mtee.__version__).
            Column {
                objectName: "aboutSettings"
                width: content.width
                visible: settings.page === "about"
                spacing: 8

                Group { title: "MTEE" }

                ValueRow { label: "Version"; value: Qt.application.version }
                ValueRow { label: "Licence"; value: "GPL-3.0" }

                Text {
                    width: parent.width
                    topPadding: 8
                    wrapMode: Text.WordWrap
                    text: "A local music library for Windows: tags, analysis, playlists and playback, with the files left where they are."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Group { title: "Third-party components" }

                Repeater {
                    model: [
                        "Python 3.12 · PSF Licence",
                        "PySide6 and Qt 6 · LGPL v3",
                        "Mutagen · GPL v2 or later",
                        "NumPy · BSD-3-Clause",
                        "pywinrt · MIT",
                        "Plus Jakarta Sans · SIL Open Font License 1.1"
                    ]

                    delegate: Text {
                        required property string modelData
                        width: content.width
                        text: modelData
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        topPadding: 6
                    }
                }
            }
        }
    }

    FileDialog {
        id: backupDialog
        title: "Back up the database"
        fileMode: FileDialog.SaveFile
        nameFilters: ["MTEE database backup (*.sqlite3)"]
        defaultSuffix: "sqlite3"
        onAccepted: dataPrivacy.backUpTo(String(selectedFile))
    }

    FileDialog {
        id: restoreDialog
        title: "Choose a backup to restore"
        nameFilters: ["MTEE database backup (*.sqlite3)"]
        onAccepted: {
            settings.backupSource = selectedFile
            settings.dialog = "restore"
        }
    }

    // Confirmation dialogs, above the page.
    Rectangle {
        id: scrim
        objectName: "privacyScrim"
        anchors.fill: parent
        visible: settings.dialog.length > 0
        color: "#B3000000"

        MouseArea {
            anchors.fill: parent
            onClicked: settings.dialog = ""
        }

        Rectangle {
            id: dialogBox
            objectName: "dialogBox"
            anchors.centerIn: parent
            width: Math.min(480, parent.width - 48)
            height: dialogColumn.implicitHeight + 40
            color: Theme.surface
            border.color: Theme.separator

            MouseArea { anchors.fill: parent }

            Column {
                id: dialogColumn
                x: 20
                y: 20
                width: parent.width - 40
                spacing: 14

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: settings.dialog === "clear-history" ? "Clear listening history?"
                        : settings.dialog === "reset-statistics" ? "Reset listening statistics?"
                        : "Restore from " + settings.backupFileName() + "?"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeTitle
                    font.weight: Font.DemiBold
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    text: settings.dialog === "clear-history"
                        ? "The History panel forgets its last 100 listenings. Your queue, your statistics and your library are not changed."
                        : settings.dialog === "reset-statistics"
                        ? "Every listening event is deleted: totals, top tracks, top albums and the chart start again from zero. This cannot be undone."
                        : "Nothing changes now. When you restart MTEE, the current database is replaced by this backup. MTEE first keeps a full copy of the current database in the restore folder; the three most recent copies are kept."
                }

                Row {
                    anchors.right: parent.right
                    spacing: 8

                    TextButton {
                        objectName: "dialogCancel"
                        text: "Cancel"
                        kind: "ghost"
                        onClicked: settings.dialog = ""
                    }

                    TextButton {
                        visible: settings.dialog === "restore"
                        objectName: "dialogSchedule"
                        text: "Schedule restore"
                        kind: "primary"
                        onClicked: {
                            dataPrivacy.restoreFrom(String(settings.backupSource))
                            settings.dialog = ""
                        }
                    }

                    DangerButton {
                        visible: settings.dialog !== "restore"
                        objectName: "dialogConfirm"
                        text: settings.dialog === "clear-history" ? "Clear history" : "Reset statistics"
                        onClicked: {
                            if (settings.dialog === "clear-history") {
                                const removed = settings.workspace.playerModel.clearHistory()
                                settings.notice = removed > 0
                                    ? "History cleared: " + removed + " entries removed."
                                    : "The History panel was already empty."
                            } else {
                                dataPrivacy.resetStatistics()
                            }
                            settings.dialog = ""
                        }
                    }
                }
            }
        }
    }

    function backupFileName() {
        const text = decodeURIComponent(String(settings.backupSource))
        const parts = text.split("/")
        return parts.length > 0 ? parts[parts.length - 1] : ""
    }

    component Group: Column {
        property string title: ""
        width: content.width
        topPadding: 20
        bottomPadding: 4
        spacing: 8

        Text {
            text: parent.title
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold
        }

        Rectangle { width: parent.width; height: 1; color: Theme.separator }
    }

    component ToggleRow: Item {
        id: toggleRow

        property string label: ""
        property string description: ""
        property bool checked: false
        signal toggled(bool checked)

        width: content.width
        height: Math.max(52, texts.implicitHeight + 16)

        Column {
            id: texts
            anchors.left: parent.left
            anchors.right: toggle.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: toggleRow.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: toggleRow.description
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        ToggleSwitch {
            id: toggle
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            checked: toggleRow.checked
            onToggled: (checked) => toggleRow.toggled(checked)
        }
    }

    component ChoiceRow: Item {
        id: choiceRow

        property string label: ""
        property string description: ""
        property var options: []
        property var current: ""
        signal chosen(var value)

        width: content.width
        height: Math.max(52, choiceTexts.implicitHeight + 16)

        Column {
            id: choiceTexts
            anchors.left: parent.left
            anchors.right: choices.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: choiceRow.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: choiceRow.description
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Row {
            id: choices
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            Repeater {
                model: choiceRow.options

                delegate: TextButton {
                    required property var modelData
                    objectName: "choice_" + modelData.value
                    implicitHeight: 28
                    text: modelData.label
                    kind: choiceRow.current === modelData.value ? "primary" : "ghost"
                    onClicked: choiceRow.chosen(modelData.value)
                }
            }
        }
    }

    component StepperRow: Item {
        id: stepperRow

        property string label: ""
        property string description: ""
        property int value: 0
        property int from: 0
        property int to: 100
        property int step: 1
        signal chosen(int value)

        width: content.width
        height: Math.max(52, stepperTexts.implicitHeight + 16)

        Column {
            id: stepperTexts
            anchors.left: parent.left
            anchors.right: stepper.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: stepperRow.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: stepperRow.description
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Row {
            id: stepper
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            TextButton {
                objectName: "stepDown"
                width: 32
                implicitHeight: 28
                text: "−"
                kind: "ghost"
                enabledAction: stepperRow.value > stepperRow.from
                onClicked: stepperRow.chosen(Math.max(stepperRow.from, stepperRow.value - stepperRow.step))
            }

            Text {
                objectName: "stepValue"
                width: 44
                height: 28
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: String(stepperRow.value)
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.features: { "tnum": 1 }
            }

            TextButton {
                objectName: "stepUp"
                width: 32
                implicitHeight: 28
                text: "+"
                kind: "ghost"
                enabledAction: stepperRow.value < stepperRow.to
                onClicked: stepperRow.chosen(Math.min(stepperRow.to, stepperRow.value + stepperRow.step))
            }
        }
    }

    component ValueRow: Item {
        id: valueRow

        property string label: ""
        property string value: ""

        width: content.width
        height: 44

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: valueRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: valueRow.value
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }

    // A label, a description and one action button on the right; optional detail line.
    component ActionRow: Item {
        id: actionRow

        property string label: ""
        property string description: ""
        property string detail: ""
        property string actionText: ""
        property bool enabledAction: true
        property bool danger: false
        signal action()

        width: content.width
        height: Math.max(60, actionTexts.implicitHeight + 16)

        Column {
            id: actionTexts
            anchors.left: parent.left
            anchors.right: actionButton.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: actionRow.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: actionRow.description
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                visible: actionRow.detail.length > 0
                width: parent.width
                text: actionRow.detail
                wrapMode: Text.WordWrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                topPadding: 4
            }
        }

        Loader {
            id: actionButton
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            sourceComponent: actionRow.danger ? dangerAction : plainAction
        }

        Component {
            id: plainAction

            TextButton {
                objectName: "action_" + actionRow.objectName
                implicitHeight: 28
                kind: "ghost"
                text: actionRow.actionText
                enabledAction: actionRow.enabledAction
                onClicked: actionRow.action()
            }
        }

        Component {
            id: dangerAction

            DangerButton {
                objectName: "action_" + actionRow.objectName
                text: actionRow.actionText
                enabledAction: actionRow.enabledAction
                onClicked: actionRow.action()
            }
        }
    }

    component DangerButton: Rectangle {
        id: danger
        property string text: ""
        property bool enabledAction: true
        signal clicked()

        implicitWidth: dangerText.implicitWidth + 28
        implicitHeight: 32
        color: dangerMouse.containsMouse && enabledAction ? Qt.lighter(Theme.danger, 1.1) : Theme.danger
        opacity: enabledAction ? 1.0 : 0.4

        Text {
            id: dangerText
            anchors.centerIn: parent
            text: danger.text
            color: Theme.textOnColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: Font.DemiBold
        }

        MouseArea {
            id: dangerMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: danger.enabledAction ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: if (danger.enabledAction) danger.clicked()
        }
    }
}
