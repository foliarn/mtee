import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Isolated review of plans 114-115: Settings categories, Profile statistics, the
// optional track columns and the confirmation dialogs. Sample data only; see
// src/mtee/prototypes/settings_profile_114.py. The frame copies the MTEE shell.
Window {
    id: root

    width: 1440
    height: 900
    minimumWidth: 900
    minimumHeight: 640
    visible: true
    color: Theme.chrome
    title: "MTEE review: settings and profile"

    readonly property string currentView: prototype.view
    property bool columnMenuOpen: false

    Shortcut {
        sequence: "Esc"
        onActivated: {
            if (prototype.dialog.length > 0) prototype.closeDialog()
            else root.columnMenuOpen = false
        }
    }

    Row {
        anchors.fill: parent

        // Activity bar, as in the application.
        Rectangle {
            id: activityBar
            width: Theme.activityBarWidth
            height: parent.height
            color: Theme.chrome

            Column {
                anchors.top: parent.top
                width: parent.width
                ActivityEntry { key: "explorer"; icon: "explorer"; tip: "Explorer" }
            }

            Column {
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 4
                width: parent.width
                ActivityEntry { key: "profile"; icon: "profile"; tip: "Profile" }
                ActivityEntry { key: "settings"; icon: "settings"; tip: "Settings (Ctrl+,)" }
            }

            component ActivityEntry: Item {
                id: entry
                required property string key
                required property string icon
                required property string tip
                readonly property bool current: root.currentView === key
                width: Theme.activityBarWidth
                height: Theme.activityBarWidth
                objectName: "activity-" + key

                Rectangle {
                    visible: entry.current
                    width: 2
                    height: parent.height
                    color: Theme.primary
                }

                Icon {
                    anchors.centerIn: parent
                    name: entry.icon
                    size: 24
                    color: entry.current || mouse.containsMouse ? Theme.textPrimary : Theme.textMuted
                }

                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: prototype.setView(entry.key)
                }

                HoverTip {
                    visible: mouse.containsMouse
                    text: entry.tip
                }
            }
        }

        Column {
            width: parent.width - activityBar.width
            height: parent.height

            // Editor tab strip with the single tab of the page.
            Rectangle {
                width: parent.width
                height: Theme.tabHeight
                color: Theme.chrome

                Rectangle {
                    x: 0
                    y: 0
                    width: tabLabel.implicitWidth + 40
                    height: parent.height
                    color: Theme.editor

                    Text {
                        id: tabLabel
                        anchors.centerIn: parent
                        text: root.currentView === "explorer" ? "Explorer"
                            : root.currentView === "profile" ? "Profile" : "Settings"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 2
                        color: Theme.primary
                    }
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Review mock-up with sample data. Nothing is saved."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeCaption
                }
            }

            Loader {
                width: parent.width
                height: parent.height - Theme.tabHeight
                sourceComponent: root.currentView === "explorer" ? explorerPage
                    : root.currentView === "profile" ? profilePage : settingsPage
            }
        }
    }

    // Confirmation dialogs, above the page.
    Rectangle {
        id: scrim
        anchors.fill: parent
        visible: prototype.dialog.length > 0
        color: "#B3000000"

        MouseArea {
            anchors.fill: parent
            onClicked: prototype.closeDialog()
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
                    text: prototype.dialog === "clear-history" ? "Clear listening history?"
                        : prototype.dialog === "reset-statistics" ? "Reset listening statistics?"
                        : "Restore from " + root.backupFile.name + "?"
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
                    lineHeight: 1.2
                    text: prototype.dialog === "clear-history"
                        ? "The History panel forgets its last 100 listenings. Your queue, your statistics and your library are not changed."
                        : prototype.dialog === "reset-statistics"
                        ? "Every listening event is deleted: totals, top tracks, top albums and the chart start again from zero. This cannot be undone."
                        : "Backup from 1 Oct 2026, with 4,212 tracks, schema version 25: checked, compatible with this build.\n\nNothing changes now. When you restart MTEE, the current database is replaced by this backup. MTEE first keeps a full copy of the current database in the restore folder."
                }

                Row {
                    anchors.right: parent.right
                    spacing: 8

                    TextButton {
                        objectName: "dialogCancel"
                        text: "Cancel"
                        kind: "ghost"
                        onClicked: prototype.closeDialog()
                    }

                    DangerButton {
                        visible: prototype.dialog !== "restore-confirm"
                        objectName: "dialogConfirm"
                        text: prototype.dialog === "clear-history" ? "Clear history" : "Reset statistics"
                        onClicked: prototype.dialog === "clear-history"
                            ? prototype.confirmClearHistory() : prototype.confirmResetStatistics()
                    }

                    TextButton {
                        visible: prototype.dialog === "restore-confirm"
                        objectName: "dialogSchedule"
                        text: "Schedule restore"
                        kind: "primary"
                        onClicked: prototype.scheduleRestore()
                    }
                }
            }
        }
    }

    // The backup chosen in the review; the real choice comes from a file dialog.
    readonly property var backupFile: ({ name: "mtee-backup-20261001.sqlite3" })

    // ---------------------------------------------------------------- Settings
    Component {
        id: settingsPage

        Row {
            id: settingsRow
            width: parent ? parent.width : 0
            height: parent ? parent.height : 0

            Rectangle {
                id: categoryList
                objectName: "settingsCategories"
                width: 220
                height: parent.height
                color: Theme.sidebar

                Column {
                    y: 24
                    width: parent.width

                    Text {
                        x: 24
                        bottomPadding: 12
                        text: "SETTINGS"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.1
                    }

                    Repeater {
                        model: prototype.categories

                        delegate: Rectangle {
                            id: categoryItem
                            required property var modelData
                            readonly property bool current: prototype.category === modelData.key
                            objectName: "category_" + modelData.key
                            width: categoryList.width
                            height: 36
                            color: current ? Theme.selection : categoryMouse.containsMouse ? Theme.surface : "transparent"

                            Rectangle {
                                visible: categoryItem.current
                                width: 2
                                height: parent.height
                                color: Theme.primary
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                x: 24
                                text: categoryItem.modelData.label
                                color: categoryItem.current ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                                font.weight: categoryItem.current ? Font.DemiBold : Font.Normal
                            }

                            MouseArea {
                                id: categoryMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: prototype.setCategory(categoryItem.modelData.key)
                            }
                        }
                    }
                }
            }

            Flickable {
                id: settingsFlick
                width: parent.width - categoryList.width
                height: parent.height
                contentHeight: settingsContent.implicitHeight + 64
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}

                Column {
                    id: settingsContent
                    x: 32
                    y: 28
                    width: Math.min(720, settingsFlick.width - 64)
                    spacing: 8

                    Text {
                        text: prototype.categories.filter(c => c.key === prototype.category)[0].label
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeHeading
                        font.weight: Font.Bold
                    }

                    Loader {
                        width: parent.width
                        sourceComponent: prototype.category === "general" ? generalCategory
                            : prototype.category === "library" ? libraryCategory
                            : prototype.category === "playback" ? playbackCategory
                            : prototype.category === "analysis" ? analysisCategory
                            : prototype.category === "shortcuts" ? shortcutsCategory
                            : prototype.category === "privacy" ? privacyCategory
                            : aboutCategory
                    }
                }
            }
        }
    }

    Component {
        id: generalCategory

        Column {
            width: parent.width
            spacing: 8

            Group { title: "Tabs" }

            ToggleRow {
                objectName: "previewTabsSetting"
                label: "Open folders and playlists in preview tabs"
                description: "Browsing reuses one italic tab instead of adding a new one each time. Double-click the tab, or sort, search or change its view, to keep it."
                checked: prototype.settings.previewTabs
                onToggled: (value) => prototype.setBool("previewTabs", value)
            }

            Text {
                topPadding: 24
                width: parent.width
                wrapMode: Text.WordWrap
                text: "General has no other setting in v0.1. The playlist creator name moved to Profile."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
    }

    Component {
        id: libraryCategory

        Column {
            width: parent.width
            spacing: 8

            Group { title: "Artist name rules" }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                topPadding: 8
                text: "Decisions you made in the Artists view. \"This is one artist\" keeps a name whole; \"Split into separate artists\" divides it. Removing a rule brings back the automatic grouping for that name."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Repeater {
                model: prototype.rules

                delegate: Item {
                    id: ruleRow
                    required property var modelData
                    width: parent.width
                    height: 52

                    Column {
                        anchors.left: parent.left
                        anchors.right: removeButton.left
                        anchors.rightMargin: 24
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        Text {
                            text: ruleRow.modelData.text
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                            elide: Text.ElideRight
                            width: parent.width
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
                        onClicked: prototype.removeRule(ruleRow.modelData.id)
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
                visible: prototype.rules.length === 0
                topPadding: 16
                width: parent.width
                text: "No rules yet. Choose \"This is one artist\" or \"Split into separate artists\" on a name in the Artists view."
                wrapMode: Text.WordWrap
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                visible: prototype.message.length > 0
                topPadding: 16
                width: parent.width
                wrapMode: Text.WordWrap
                text: prototype.message
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
    }

    Component {
        id: playbackCategory

        Column {
            width: parent.width
            spacing: 8

            Group { title: "Player" }

            ToggleRow {
                objectName: "islandSetting"
                label: "Show player island"
                description: "Floating player at the bottom of the editor while a track is loaded. Also in View › Player island."
                checked: prototype.settings.island
                onToggled: (value) => prototype.setBool("island", value)
            }

            Group { title: "Loudness" }

            ToggleRow {
                objectName: "normalizationSetting"
                label: "Normalize loudness"
                description: "Play analyzed tracks at a similar loudness, using the loudness measured by Analyze. Tracks not analyzed yet play as they are. The files are never changed."
                checked: prototype.settings.normalize
                onToggled: (value) => prototype.setBool("normalize", value)
            }

            ChoiceRow {
                objectName: "normalizationLevelSetting"
                label: "Loudness target"
                description: "Quiet -23 LUFS, Normal -14 LUFS, Loud -11 LUFS. Louder tracks are turned down; quieter ones are turned up, never past -1 dBFS peak."
                options: [{ "value": "quiet", "label": "Quiet" }, { "value": "normal", "label": "Normal" }, { "value": "loud", "label": "Loud" }]
                current: prototype.settings.level
                onChosen: (value) => prototype.setText("level", value)
            }
        }
    }

    Component {
        id: analysisCategory

        Column {
            width: parent.width
            spacing: 8

            Text {
                width: parent.width
                topPadding: 4
                text: "Tracks are analyzed only when you ask: right-click a track or a folder and choose Analyze. Results are stored permanently."
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Group { title: "Key" }

            ChoiceRow {
                label: "Key notation"
                description: "How keys are written in the track list, the inspector and the player: Camelot (8A) or classic (Am)."
                options: [{ "value": "camelot", "label": "Camelot" }, { "value": "classic", "label": "Classic" }]
                current: prototype.settings.notation
                onChosen: (value) => prototype.setText("notation", value)
            }

            Group { title: "Tempo" }

            StepperRow {
                label: "Lowest BPM"
                description: "Tempos are halved or doubled to fall inside the range. The highest BPM is always at least twice the lowest."
                value: prototype.settings.bpmMin
                from: 40
                to: 150
                step: 5
                onChosen: (value) => prototype.setInt("bpmMin", value)
            }

            StepperRow {
                label: "Highest BPM"
                description: "Narrow the range to settle half-time or double-time ambiguity, for example 90 to 180."
                value: prototype.settings.bpmMax
                from: 80
                to: 300
                step: 5
                onChosen: (value) => prototype.setInt("bpmMax", value)
            }

            ChoiceRow {
                label: "BPM decimals shown"
                description: "Analyzed tempos are stored with more precision than they are shown."
                options: [{ "value": 0, "label": "0" }, { "value": 1, "label": "1" }, { "value": 2, "label": "2" }]
                current: prototype.settings.decimals
                onChosen: (value) => prototype.setInt("decimals", value)
            }

            Group { title: "Processing" }

            StepperRow {
                label: "Analyses in parallel"
                description: "Tracks analyzed at the same time. A higher number is faster but slows the rest of MTEE while a batch runs."
                value: prototype.settings.parallel
                from: 1
                to: 8
                step: 1
                onChosen: (value) => prototype.setInt("parallel", value)
            }

            ToggleRow {
                label: "Write results into the file tags"
                description: "After an analysis, copy BPM and key into the tags of the audio file, replacing the ones already there. This rewrites each file. Off by default."
                checked: prototype.settings.writeTags
                onToggled: (value) => prototype.setBool("writeTags", value)
            }
        }
    }

    Component {
        id: shortcutsCategory

        Column {
            width: parent.width
            spacing: 0

            Text {
                width: parent.width
                topPadding: 4
                bottomPadding: 12
                text: "Read-only list of the shortcuts MTEE handles. Shortcuts that depend on a selection work only while that selection exists."
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Repeater {
                model: prototype.shortcuts

                delegate: Item {
                    id: shortcutRow
                    required property var modelData
                    required property int index
                    width: parent.width
                    height: 36

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: shortcutRow.modelData.action
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                    }

                    Rectangle {
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
    }

    Component {
        id: privacyCategory

        Column {
            width: parent.width
            spacing: 8

            Group { title: "Listening history" }

            ActionRow {
                objectName: "clearHistoryRow"
                label: "Clear listening history"
                description: "Empties the History panel, which keeps the last 100 listenings. Your statistics are not changed."
                detail: prototype.historyCount + " of 100 entries"
                actionText: "Clear history…"
                enabledAction: prototype.historyCount > 0
                onAction: prototype.openDialog("clear-history")
            }

            Group { title: "Statistics" }

            ActionRow {
                objectName: "resetStatisticsRow"
                label: "Reset listening statistics"
                description: "Deletes every listening event: totals, top tracks, top albums and the chart. The installation identifier is kept. This cannot be undone."
                actionText: "Reset statistics…"
                danger: true
                onAction: prototype.openDialog("reset-statistics")
            }

            Group { title: "Database" }

            ActionRow {
                objectName: "backUpRow"
                label: "Back up database"
                description: "Writes a consistent copy of the library database to a file you choose, and checks it. An existing file is never overwritten."
                detail: prototype.lastBackup.length > 0 ? "Last: " + prototype.lastBackup : "No backup yet"
                actionText: "Back up…"
                onAction: prototype.backUp()
            }

            ActionRow {
                objectName: "restoreRow"
                label: "Restore database"
                description: "Choose a backup to restore. It is checked first and applied the next time MTEE starts; a copy of the current database is kept."
                detail: prototype.restorePending ? "Restore scheduled. Restart MTEE to apply it." : ""
                actionText: prototype.restorePending ? "Cancel restore" : "Restore from backup…"
                onAction: prototype.restorePending ? prototype.cancelRestore() : prototype.chooseBackupFile()
            }

            Text {
                visible: prototype.message.length > 0
                topPadding: 16
                width: parent.width
                wrapMode: Text.WordWrap
                text: prototype.message
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
    }

    Component {
        id: aboutCategory

        Column {
            width: parent.width
            spacing: 8

            Group { title: "MTEE" }

            Text {
                topPadding: 8
                text: "MTEE 0.1.0"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.DemiBold
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "A local music library for Windows: tags, analysis, playlists and playback, with the files left where they are."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Text {
                width: parent.width
                topPadding: 8
                wrapMode: Text.WordWrap
                text: "Licence of MTEE: not decided yet."
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
                    width: parent.width
                    text: modelData
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    topPadding: 6
                }
            }

            Item {
                width: 1
                height: 12
            }

            TextButton {
                text: "Open the full notices"
                kind: "ghost"
                enabledAction: false
                tip: "Opens THIRD_PARTY_NOTICES.md and LICENSES/ in the real build"
            }
        }
    }

    // ----------------------------------------------------------------- Profile
    Component {
        id: profilePage

        Flickable {
            id: profileFlick
            objectName: "profilePage"
            width: parent ? parent.width : 0
            height: parent ? parent.height : 0
            contentHeight: profileContent.implicitHeight + 64
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}

            Column {
                id: profileContent
                x: 32
                y: 28
                width: Math.min(880, profileFlick.width - 64)
                spacing: 24

                Row {
                    spacing: 24
                    width: parent.width

                    Rectangle {
                        id: avatarFrame
                        width: 112
                        height: 112
                        color: Theme.surface
                        clip: true

                        Image {
                            objectName: "profileAvatar"
                            anchors.fill: parent
                            source: prototype.avatarSource
                            fillMode: Image.PreserveAspectCrop
                            visible: prototype.avatarSource.length > 0
                        }

                        Icon {
                            anchors.centerIn: parent
                            visible: prototype.avatarSource.length === 0
                            name: "profile"
                            size: 48
                            color: Theme.textMuted
                        }
                    }

                    Column {
                        width: parent.width - avatarFrame.width - 24
                        spacing: 10

                        Text {
                            text: prototype.profileName
                            color: Theme.textPrimary
                            font.family: Theme.displayFontFamily
                            font.pixelSize: 30
                            font.weight: Theme.displayFontWeight
                            elide: Text.ElideRight
                            width: parent.width
                        }

                        Text {
                            text: "Shown as the creator of your playlists. Stored on this computer only."
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        Row {
                            spacing: 8

                            TextButton {
                                objectName: "chooseAvatar"
                                text: "Change picture…"
                                kind: "ghost"
                                onClicked: prototype.chooseAvatar()
                            }

                            TextButton {
                                objectName: "removeAvatar"
                                text: "Remove picture"
                                kind: "ghost"
                                enabledAction: prototype.avatarSource.length > 0
                                onClicked: prototype.removeAvatar()
                            }
                        }
                    }
                }

                Row {
                    spacing: 8
                    width: parent.width

                    TextField {
                        id: nameField
                        objectName: "displayNameInput"
                        width: Math.min(340, parent.width - 120)
                        height: 36
                        text: prototype.profileName
                        maximumLength: 240
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                        background: Rectangle { color: Theme.surface; border.color: nameField.activeFocus ? Theme.focus : Theme.separator }
                        onAccepted: prototype.setDisplayName(text)
                    }

                    TextButton {
                        objectName: "saveDisplayName"
                        implicitHeight: 36
                        text: "Save name"
                        kind: "primary"
                        onClicked: prototype.setDisplayName(nameField.text)
                    }
                }

                Text {
                    visible: prototype.message.length > 0
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: prototype.message
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                // Statistics
                Rectangle { width: parent.width; height: 1; color: Theme.separator }

                Row {
                    width: parent.width
                    spacing: 16

                    Item {
                        width: parent.width - periodRow.width - 16
                        height: periodRow.height

                        Text {
                            id: statsTitle
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Listening"
                            color: Theme.textPrimary
                            font.family: Theme.displayFontFamily
                            font.pixelSize: Theme.fontSizeTitle
                            font.weight: Font.Bold
                        }
                    }

                    Row {
                        id: periodRow
                        objectName: "periodSelector"
                        spacing: 4

                        Repeater {
                            model: prototype.periods

                            delegate: TextButton {
                                required property var modelData
                                objectName: "period_" + modelData.key
                                implicitHeight: 28
                                text: modelData.label
                                kind: prototype.period === modelData.key ? "primary" : "ghost"
                                onClicked: prototype.setPeriod(modelData.key)
                            }
                        }
                    }
                }

                Row {
                    spacing: 12
                    width: parent.width

                    Kpi { objectName: "kpiListening"; label: "Listening time"; value: prototype.stats.listening; width: (parent.width - 24) / 3 }
                    Kpi { objectName: "kpiPlays"; label: "Plays"; value: prototype.stats.plays; width: (parent.width - 24) / 3 }
                    Kpi { objectName: "kpiSessions"; label: "Listening sessions"; value: prototype.stats.sessions; width: (parent.width - 24) / 3 }
                }

                // Chart
                Column {
                    width: parent.width
                    spacing: 8

                    Text {
                        text: "Listening over time · " + prototype.periodLabel
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        font.weight: Font.DemiBold
                    }

                    Item {
                        id: chart
                        objectName: "listeningChart"
                        width: parent.width
                        height: 176

                        readonly property var bars: prototype.stats.series ? prototype.stats.series : []
                        readonly property real peak: {
                            let top = 1
                            for (let i = 0; i < bars.length; i++)
                                top = Math.max(top, bars[i].minutes)
                            return top
                        }
                        readonly property int labelStep: bars.length > 12 ? Math.ceil(bars.length / 6) : 1
                        readonly property real barSpacing: 3
                        readonly property real barWidth: bars.length > 0
                            ? (width - barSpacing * (bars.length - 1)) / bars.length : 0

                        Rectangle {
                            width: parent.width
                            height: 1
                            y: 120
                            color: Theme.separator
                        }

                        Row {
                            id: barRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            height: 120
                            spacing: chart.barSpacing

                            Repeater {
                                model: chart.bars

                                delegate: Item {
                                    id: barItem
                                    required property var modelData
                                    required property int index
                                    width: chart.barWidth
                                    height: barRow.height

                                    Rectangle {
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: barItem.modelData.minutes > 0
                                            ? Math.max(2, barItem.modelData.minutes / chart.peak * barRow.height) : 0
                                        color: barMouse.containsMouse ? Theme.primaryHover : Theme.primary
                                    }

                                    MouseArea {
                                        id: barMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                    }

                                    HoverTip {
                                        visible: barMouse.containsMouse
                                        text: barItem.modelData.label + " · " + barItem.modelData.minutes + " min"
                                    }
                                }
                            }
                        }

                        // Labels sit at the position of their bar, so they never shift with
                        // the Row layout; only every labelStep-th bar carries a label.
                        Item {
                            anchors.top: barRow.bottom
                            anchors.topMargin: 8
                            anchors.left: parent.left
                            anchors.right: parent.right
                            height: 16

                            Repeater {
                                model: chart.bars

                                delegate: Text {
                                    required property var modelData
                                    required property int index
                                    x: index * (chart.barWidth + chart.barSpacing)
                                    width: chart.barWidth * chart.labelStep
                                    visible: index % chart.labelStep === 0
                                    text: modelData.label
                                    elide: Text.ElideNone
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeCaption
                                }
                            }
                        }
                    }
                }

                // Rankings
                Row {
                    width: parent.width
                    spacing: 24

                    RankingList {
                        objectName: "topTracks"
                        width: (parent.width - 48) / 3
                        heading: "Top tracks"
                        rows: prototype.stats.tracks
                        emptyText: "No plays in this period."
                        primaryKey: "title"
                        secondaryKey: "artist"
                    }

                    RankingList {
                        objectName: "topArtists"
                        width: (parent.width - 48) / 3
                        heading: "Top artists"
                        rows: prototype.stats.artists
                        emptyText: "Artists appear once the artist name rules are set up (step 112)."
                        primaryKey: "name"
                        secondaryKey: ""
                    }

                    RankingList {
                        objectName: "topAlbums"
                        width: (parent.width - 48) / 3
                        heading: "Top albums"
                        rows: prototype.stats.albums
                        emptyText: "No plays in this period."
                        primaryKey: "name"
                        secondaryKey: ""
                    }
                }

                Text {
                    width: parent.width
                    bottomPadding: 24
                    wrapMode: Text.WordWrap
                    text: "Plays count a track once 30 seconds were heard, or once a track shorter than 30 seconds is played to its end. Periods use the local calendar; weeks start on Monday."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
        }
    }

    // ---------------------------------------------------------------- Explorer
    Component {
        id: explorerPage

        Column {
            width: parent.width
            height: parent.height

            Item {
                id: trackHeader
                width: parent.width
                height: 40

                Row {
                    anchors.left: parent.left
                    anchors.right: columnsButton.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0

                    Repeater {
                        model: root.columnDefinitions

                        delegate: Item {
                            id: headCell
                            required property var modelData
                            width: root.columnWidth(modelData.key)
                            height: 40
                            visible: root.columnVisible(modelData.key)

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                text: headCell.modelData.label.toUpperCase()
                                color: prototype.sort === headCell.modelData.key ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeCaption
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1.1
                            }

                            MouseArea {
                                anchors.fill: parent
                                enabled: headCell.modelData.sortable === true
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: prototype.sortBy(headCell.modelData.key === "plays" ? "plays" : "title")
                            }
                        }
                    }
                }

                TextButton {
                    id: columnsButton
                    objectName: "columnsButton"
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    implicitHeight: 28
                    kind: "ghost"
                    text: "Columns"
                    icon: "more"
                    onClicked: root.columnMenuOpen = !root.columnMenuOpen
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.separator
                }
            }

            ListView {
                id: trackList
                objectName: "trackList"
                width: parent.width
                height: parent.height - trackHeader.height
                clip: true
                model: prototype.tracks
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}

                delegate: Item {
                    id: trackRow
                    required property var modelData
                    required property int index
                    width: trackList.width
                    height: 36

                    Rectangle {
                        anchors.fill: parent
                        color: rowMouse.containsMouse ? Theme.surface : "transparent"
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 0

                        Repeater {
                            model: root.columnDefinitions

                            delegate: Text {
                                required property var modelData
                                width: root.columnWidth(modelData.key)
                                visible: root.columnVisible(modelData.key)
                                leftPadding: 8
                                text: String(trackRow.modelData[modelData.key])
                                elide: Text.ElideRight
                                color: modelData.key === "title" ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                                font.features: { "tnum": 1 }
                            }
                        }
                    }

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                    }
                }
            }
        }
    }

    // Column chooser: the two statistics columns are optional, off by default.
    Rectangle {
        id: columnMenu
        objectName: "columnMenu"
        visible: root.columnMenuOpen && root.currentView === "explorer"
        x: root.width - width - 24
        y: 80
        width: 260
        height: menuColumn.implicitHeight + 16
        color: Theme.surface
        border.color: Theme.separator
        z: 50

        Column {
            id: menuColumn
            x: 8
            y: 8
            width: parent.width - 16

            Text {
                text: "COLUMNS"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
                font.weight: Font.DemiBold
                font.letterSpacing: 1.1
                leftPadding: 8
                topPadding: 4
                bottomPadding: 8
            }

            Repeater {
                model: [
                    { "key": "plays", "label": "Plays" },
                    { "key": "lastPlayed", "label": "Last played" }
                ]

                delegate: Rectangle {
                    id: menuItem
                    required property var modelData
                    objectName: "column_" + modelData.key
                    width: menuColumn.width
                    height: 36
                    color: menuItemMouse.containsMouse ? Theme.selection : "transparent"

                    Icon {
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        name: "check"
                        size: 16
                        visible: prototype.columns[menuItem.modelData.key] === true
                        color: Theme.primary
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 36
                        anchors.verticalCenter: parent.verticalCenter
                        text: menuItem.modelData.label
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    MouseArea {
                        id: menuItemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: prototype.setColumn(menuItem.modelData.key, !(prototype.columns[menuItem.modelData.key] === true))
                    }
                }
            }

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                leftPadding: 8
                topPadding: 8
                bottomPadding: 4
                text: "Plays counts the listenings that count as a play. Last played is the start of the latest listening."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
            }
        }
    }

    readonly property var columnDefinitions: [
        { "key": "title", "label": "Title", "sortable": false },
        { "key": "artist", "label": "Artist", "sortable": false },
        { "key": "album", "label": "Album", "sortable": false },
        { "key": "key", "label": "Key", "sortable": false },
        { "key": "bpm", "label": "BPM", "sortable": false },
        { "key": "length", "label": "Time", "sortable": false },
        { "key": "plays", "label": "Plays", "sortable": true },
        { "key": "lastPlayed", "label": "Last played", "sortable": false }
    ]

    function columnVisible(key) {
        if (key === "plays" || key === "lastPlayed")
            return prototype.columns[key] === true
        return true
    }

    function columnWidth(key) {
        switch (key) {
        case "title": return 300
        case "artist": return 200
        case "album": return 200
        case "key": return 56
        case "bpm": return 56
        case "length": return 64
        case "plays": return 72
        case "lastPlayed": return 128
        }
        return 100
    }

    // ------------------------------------------------------------ Components
    component Group: Column {
        property string title: ""
        width: parent ? parent.width : 0
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
        signal toggled(bool value)

        width: parent ? parent.width : 0
        height: Math.max(52, toggleTexts.implicitHeight + 16)

        Column {
            id: toggleTexts
            anchors.left: parent.left
            anchors.right: toggleSwitch.left
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
            id: toggleSwitch
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            checked: toggleRow.checked
            onToggled: (value) => toggleRow.toggled(value)
        }
    }

    component ChoiceRow: Item {
        id: choiceRow
        property string label: ""
        property string description: ""
        property var options: []
        property var current: ""
        signal chosen(var value)

        width: parent ? parent.width : 0
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

        width: parent ? parent.width : 0
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
                width: 32
                implicitHeight: 28
                text: "−"
                kind: "ghost"
                enabledAction: stepperRow.value > stepperRow.from
                onClicked: stepperRow.chosen(Math.max(stepperRow.from, stepperRow.value - stepperRow.step))
            }

            Text {
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
                width: 32
                implicitHeight: 28
                text: "+"
                kind: "ghost"
                enabledAction: stepperRow.value < stepperRow.to
                onClicked: stepperRow.chosen(Math.min(stepperRow.to, stepperRow.value + stepperRow.step))
            }
        }
    }

    component ActionRow: Item {
        id: actionRow
        property string label: ""
        property string description: ""
        property string detail: ""
        property string actionText: ""
        property bool enabledAction: true
        property bool danger: false
        signal action()

        width: parent ? parent.width : 0
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
                objectName: "action_" + actionRow.label.replace(/ /g, "_")
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
                objectName: "action_" + actionRow.label.replace(/ /g, "_")
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

    component Kpi: Rectangle {
        id: kpi
        property string label: ""
        property string value: ""

        height: 84
        color: Theme.surface

        Column {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Text {
                text: kpi.label
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                text: kpi.value
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 24
                font.weight: Theme.displayFontWeight
                font.features: { "tnum": 1 }
            }
        }
    }

    component RankingList: Column {
        id: ranking
        property string heading: ""
        property var rows: []
        property string emptyText: ""
        property string primaryKey: ""
        property string secondaryKey: ""

        spacing: 8

        Text {
            text: ranking.heading
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold
        }

        Rectangle { width: parent.width; height: 1; color: Theme.separator }

        Repeater {
            model: ranking.rows.slice(0, 5)

            delegate: Item {
                id: rankItem
                required property var modelData
                required property int index
                width: ranking.width
                height: 40

                Text {
                    id: rankNumber
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    text: String(rankItem.index + 1)
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    font.features: { "tnum": 1 }
                }

                Column {
                    anchors.left: rankNumber.right
                    anchors.right: plays.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        width: parent.width
                        text: rankItem.modelData[ranking.primaryKey]
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    Text {
                        visible: ranking.secondaryKey.length > 0
                        width: parent.width
                        text: ranking.secondaryKey.length > 0 ? rankItem.modelData[ranking.secondaryKey] : ""
                        elide: Text.ElideRight
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }

                Text {
                    id: plays
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: rankItem.modelData.plays !== undefined ? rankItem.modelData.plays : rankItem.modelData.countedPlays
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    font.features: { "tnum": 1 }
                }
            }
        }

        Text {
            visible: ranking.rows.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            topPadding: 6
            text: ranking.emptyText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
