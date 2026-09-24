import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Convert tab: input files on the left, output settings on the right. The
// options are invented for the review; the real ones will come from the FFmpeg
// shipped with MTEE (plan 07). Sources are never modified.
Rectangle {
    id: convert

    objectName: "convertView"
    required property var workspace
    property int bottomInset: 0
    property bool advancedOpen: false
    property bool started: workspace.conversionError
    property int formatIndex: 0
    readonly property var formats: [
        { "name": "MP3", "quality": "320 kbps · CBR" },
        { "name": "AIFF", "quality": "16-bit · 44.1 kHz" },
        { "name": "FLAC", "quality": "Level 5 · lossless" },
        { "name": "WAV", "quality": "16-bit PCM" }
    ]
    readonly property var inputs: workspace.convertInputs

    color: Theme.editor

    Item {
        id: heading
        width: parent.width
        height: 92

        Column {
            x: 24
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            spacing: 2

            SectionLabel { text: "Convert" }

            Row {
                spacing: 14

                Text {
                    id: title
                    text: "New conversion"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                }

                Text {
                    anchors.baseline: title.baseline
                    text: convert.inputs.length + " files · " + convert.formats[convert.formatIndex].name
                        + " " + convert.formats[convert.formatIndex].quality
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 24
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            spacing: 8

            TextButton { kind: "ghost"; icon: "plus"; text: "Add files"; enabledAction: false; tip: "Not available in the demo" }
            TextButton {
                kind: "neutral"
                icon: "plus"
                text: "Add selected tracks"
                enabledAction: convert.workspace.selectedIds.length > 0
                onClicked: convert.workspace.addSelectionToConvert()
            }
        }
    }

    Item {
        id: body
        anchors.top: heading.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: summary.top
        anchors.leftMargin: 24
        anchors.rightMargin: 24

        Item {
            id: inputsPane
            anchors.left: parent.left
            anchors.right: settings.left
            anchors.rightMargin: 24
            height: parent.height

            SectionLabel { id: inputsLabel; text: "Input files" }

            ListView {
                anchors.top: inputsLabel.bottom
                anchors.topMargin: 10
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                clip: true
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                model: convert.inputs
                ScrollBar.vertical: ThinScrollBar {}

                delegate: Rectangle {
                    id: entry
                    required property var modelData
                    required property int index
                    readonly property bool failed: convert.workspace.conversionError && index === 1

                    width: ListView.view.width
                    height: 64
                    color: failed ? Qt.rgba(1, 0.3, 0.3, 0.08) : entryMouse.containsMouse ? Theme.surface : Theme.sidebar

                    MouseArea { id: entryMouse; anchors.fill: parent; hoverEnabled: true }

                    Rectangle {
                        visible: entry.failed
                        width: 2
                        height: parent.height
                        color: Theme.danger
                    }

                    CoverArt {
                        id: art
                        x: 14
                        anchors.verticalCenter: parent.verticalCenter
                        width: 40
                        height: 40
                        pattern: entry.modelData.cover
                    }

                    Column {
                        anchors.left: art.right
                        anchors.leftMargin: 12
                        anchors.right: status.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3

                        Text {
                            width: parent.width
                            text: entry.modelData.filename
                            elide: Text.ElideMiddle
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSecondary
                        }

                        Text {
                            width: parent.width
                            text: entry.failed
                                ? "Could not write the output. The source file is untouched."
                                : entry.modelData.format + " · " + entry.modelData.bitrate + " · " + entry.modelData.duration
                            elide: Text.ElideRight
                            color: entry.failed ? Theme.danger : Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        ProgressLine {
                            visible: convert.started
                            width: parent.width
                            progress: entry.failed ? 0.62 : 1
                            status: entry.failed ? "error" : "done"
                        }
                    }

                    Item {
                        id: status
                        anchors.right: parent.right
                        anchors.rightMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        width: statusRow.implicitWidth
                        height: 28

                        Row {
                            id: statusRow
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: !entry.failed
                                text: convert.started ? "Converted" : "Ready"
                                color: convert.started ? Theme.primary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }

                            TextButton {
                                visible: entry.failed
                                implicitHeight: 28
                                kind: "neutral"
                                text: "Retry"
                                onClicked: convert.workspace.retryConversion()
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            id: settings
            anchors.right: parent.right
            width: Math.min(360, parent.width * 0.42)
            height: parent.height
            color: Theme.sidebar

            Flickable {
                anchors.fill: parent
                contentHeight: form.implicitHeight + 32
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}

                Column {
                    id: form
                    x: 16
                    y: 16
                    width: parent.width - 32
                    spacing: 14

                    SectionLabel { text: "Output" }

                    Setting {
                        label: "Format"
                        value: convert.formats[convert.formatIndex].name
                        chooser: true
                        onActivated: convert.formatIndex = (convert.formatIndex + 1) % convert.formats.length
                    }

                    Setting {
                        label: "Quality"
                        value: convert.formats[convert.formatIndex].quality
                        chooser: true
                    }

                    Setting {
                        label: "Output folder"
                        value: "Music/Converted/" + convert.formats[convert.formatIndex].name
                        action: "Choose…"
                    }

                    Rectangle {
                        width: parent.width
                        height: 32
                        color: advancedMouse.containsMouse ? Theme.surface : "transparent"

                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 4

                            Icon {
                                anchors.verticalCenter: parent.verticalCenter
                                name: convert.advancedOpen ? "chevron-down" : "chevron-right"
                                size: 16
                                color: Theme.textSecondary
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Advanced"
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                            }
                        }

                        MouseArea {
                            id: advancedMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: convert.advancedOpen = !convert.advancedOpen
                        }
                    }

                    Column {
                        visible: convert.advancedOpen
                        width: parent.width
                        spacing: 14

                        Setting { label: "Sample rate"; value: "44.1 kHz"; chooser: true }
                        Setting { label: "Channels"; value: "Stereo"; chooser: true }
                        Setting { label: "Metadata"; value: "Copy compatible tags"; chooser: true }
                    }

                    TextButton {
                        width: parent.width
                        kind: "primary"
                        text: "Start conversion"
                        onClicked: convert.started = true
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Demo options. The formats offered will come from the FFmpeg shipped with MTEE. Existing files are never overwritten."
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }
            }
        }
    }

    Rectangle {
        id: summary
        anchors.bottom: parent.bottom
        anchors.bottomMargin: convert.bottomInset
        width: parent.width
        height: 52
        color: Theme.editor

        Rectangle {
            x: 24
            width: parent.width - 48
            height: 1
            color: Theme.separator
        }

        Row {
            x: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            Icon {
                anchors.verticalCenter: parent.verticalCenter
                visible: convert.workspace.conversionError
                name: "alert"
                size: 16
                color: Theme.danger
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: !convert.started ? convert.inputs.length + " files ready"
                    : convert.workspace.conversionError ? "1 of 2 converted · 1 failed. Retry the failed file after checking the output folder."
                    : convert.inputs.length + " of " + convert.inputs.length + " converted"
                color: convert.workspace.conversionError ? Theme.danger : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            TextButton { implicitHeight: 28; kind: "ghost"; text: "Cancel pending"; enabledAction: false }
            TextButton { implicitHeight: 28; kind: "ghost"; text: "Open output folder"; enabledAction: convert.started; tip: "Simulated in the demo" }
        }
    }

    component Setting: Column {
        id: setting

        property string label: ""
        property string value: ""
        property bool chooser: false
        property string action: ""
        signal activated()

        width: parent ? parent.width : 0
        spacing: 4

        Text {
            text: setting.label
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Rectangle {
            width: parent.width
            height: 32
            color: Theme.chrome
            border.width: 1
            border.color: settingMouse.containsMouse ? Theme.textMuted : Theme.separator

            Text {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.right: trailing.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: setting.value
                elide: Text.ElideMiddle
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Item {
                id: trailing
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                width: setting.action.length > 0 ? actionText.implicitWidth : 16
                height: 16

                Icon {
                    visible: setting.chooser
                    name: "chevron-down"
                    size: 16
                    color: Theme.textSecondary
                }

                Text {
                    id: actionText
                    visible: setting.action.length > 0
                    anchors.verticalCenter: parent.verticalCenter
                    text: setting.action
                    color: Theme.primary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            MouseArea {
                id: settingMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: setting.activated()
            }
        }
    }
}
