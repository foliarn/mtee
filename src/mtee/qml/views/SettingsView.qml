import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Settings editor tab, as in VS Code, with a General and an Analysis page. In
// General only the player island switch acts on the prototype; the other entries
// show where future settings will live. The Analysis page is fully functional.
Rectangle {
    id: settings

    objectName: "settingsView"
    required property var workspace
    property int groupIndex: 0
    property int bottomInset: 0
    property bool rememberQueue: false
    readonly property string page: workspace.settingsPageForGroup(groupIndex)
    readonly property var analysis: workspace.analysisSettings

    color: Theme.editor

    Flickable {
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

            Column {
                visible: settings.page === "general" && typeof settings.workspace.playlistModel !== "undefined"
                width: parent.width
                spacing: 8
                Text { text: "Playlist creator name"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 16 }
                TextField {
                    objectName: "playlistCreatorInput"
                    width: Math.min(340, parent.width); height: 36
                    text: typeof settings.workspace.playlistModel !== "undefined" ? settings.workspace.playlistModel.creator : ""
                    color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 16
                    onEditingFinished: if (typeof settings.workspace.playlistModel !== "undefined") settings.workspace.playlistModel.setCreator(text)
                    background: Rectangle { color: Theme.surface; border.color: parent.activeFocus ? Theme.focus : Theme.separator }
                }
            }

            Row {
                objectName: "settingsTabs"
                height: Theme.tabHeight

                Repeater {
                    model: [{ "key": "general", "label": "General" }, { "key": "analysis", "label": "Analysis" }]

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

            Column {
                id: generalPage
                width: content.width
                visible: settings.page === "general"
                spacing: 8

                Group { title: "Playback" }

                ToggleRow {
                    objectName: "islandSetting"
                    label: "Show player island"
                    description: "Floating player at the bottom of the editor while a track is loaded. Also in View › Player island."
                    checked: settings.workspace.islandEnabled
                    onToggled: (checked) => settings.workspace.setIslandEnabled(checked)
                }

                ToggleRow {
                    label: "Remember the queue between sessions"
                    description: "Restore the last queue and position when MTEE starts."
                    checked: settings.rememberQueue
                    onToggled: (checked) => settings.rememberQueue = checked
                }

                Group { title: "Library" }

                ValueRow { label: "Folders"; value: "Music"; action: "Add folder" }

                Group { title: "Appearance" }

                ValueRow { label: "Theme"; value: "Acid (dark)" }
                ValueRow { label: "Density"; value: "Comfortable" }

                Group { title: "Keyboard shortcuts" }

                Grid {
                    width: parent.width
                    columns: 2
                    columnSpacing: 24
                    rowSpacing: 10
                    topPadding: 4

                    Repeater {
                        model: [
                            "Play or pause", "Space",
                            "Play the selected track", "Enter or double-click",
                            "Edit info", "Ctrl+I",
                            "Select all", "Ctrl+A",
                            "Show Explorer", "Ctrl+Shift+E",
                            "Toggle sidebar", "Ctrl+B",
                            "Split editor", "Ctrl+\\",
                            "Fullscreen player", "F11",
                            "Next / previous track", "Ctrl+→ / Ctrl+←",
                            "Settings", "Ctrl+,"
                        ]
                        delegate: Text {
                            required property string modelData
                            required property int index
                            width: index % 2 === 0 ? 280 : implicitWidth
                            text: modelData
                            color: index % 2 === 0 ? Theme.textPrimary : Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSecondary
                        }
                    }
                }
            }

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
        }
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
                text: "\u2212"
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
        property string action: ""

        width: content.width
        height: 44

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: valueRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: valueRow.value
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                visible: valueRow.action.length > 0
                implicitHeight: 28
                kind: "ghost"
                text: valueRow.action
                enabledAction: false
                tip: "Not available in the demo"
            }
        }
    }
}
