import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// Convert tab: inspect a batch, review destinations, then create verified copies.
Rectangle {
    id: convert

    objectName: "convertView"
    required property var workspace
    property int bottomInset: 0
    property bool advancedOpen: false
    readonly property bool started: convert.inputs.some(function (item) {
        return item.status === "completed" || item.status === "failed" || item.status === "cancelled"
    })
    readonly property int formatIndex: convert.workspace.conversionModel.formatIndex
    readonly property var formats: convert.workspace.conversionModel.formats
    readonly property var inputs: workspace.convertInputs

    FolderDialog {
        id: outputFolderDialog
        title: "Choose output folder"
        onAccepted: convert.workspace.conversionModel.set_output_folder(selectedFolder.toString())
    }

    FileDialog {
        id: inputFilesDialog
        title: "Add audio files"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Audio files (*.mp3 *.flac *.wav *.aiff *.ogg *.opus *.m4a *.aac *.adts)", "All files (*)"]
        onAccepted: convert.workspace.conversionModel.add_files(selectedFiles)
    }

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

            TextButton {
                kind: "ghost"
                icon: "plus"
                text: "Add files"
                onClicked: inputFilesDialog.open()
            }

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
                    readonly property bool failed: ["failed", "conflict", "unsupported", "cancelled"].indexOf(entry.modelData.status) >= 0
                    readonly property bool completed: entry.modelData.status === "completed"
                    readonly property bool running: entry.modelData.status === "running"

                    width: ListView.view.width
                    height: 64
                    color: failed ? Qt.rgba(1, 0.3, 0.3, 0.08) : entryMouse.containsMouse ? Theme.surface : Theme.sidebar
                    ToolTip.visible: entryMouse.containsMouse && entry.modelData.metadataReport.length > 0
                    ToolTip.delay: 700
                    ToolTip.text: entry.modelData.metadataReport

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
                        text: entry.failed ? entry.modelData.summary
                            : entry.completed ? entry.modelData.destination
                            : entry.modelData.format + " · " + entry.modelData.bitrate + " · " + entry.modelData.duration
                            elide: Text.ElideRight
                            color: entry.failed ? Theme.danger : Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        ProgressLine {
                        visible: entry.running || entry.completed || entry.failed
                        progress: Number(entry.modelData.progress || 0) / 100
                        status: entry.failed ? "error" : entry.completed ? "done" : "running"
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
                                text: entry.completed ? "Converted"
                                    : entry.failed ? "Failed"
                                    : entry.running ? "Converting " + entry.modelData.progress + "%"
                                    : "Ready"
                                color: entry.completed ? Theme.primary : entry.failed ? Theme.danger : Theme.textSecondary
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
                        value: convert.formats.length ? convert.formats[convert.formatIndex].name : "Unavailable"
                        chooser: true
                        onActivated: convert.workspace.conversionModel.next_format()
                    }

                    Setting {
                        label: "Quality"
                        value: convert.formats.length ? convert.formats[convert.formatIndex].quality : "Unavailable"
                        chooser: true
                        onActivated: convert.workspace.conversionModel.next_quality()
                    }

                    Setting {
                        label: "Output folder"
                        value: convert.workspace.conversionModel.outputFolder
                        action: "Choose…"
                        onActivated: outputFolderDialog.open()
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

                        Setting {
                            label: "Sample rate"
                            value: convert.workspace.conversionModel.sampleRate
                            chooser: convert.workspace.conversionModel.sampleRateOptions.length > 1
                            onActivated: convert.workspace.conversionModel.next_sample_rate()
                        }
                        Setting {
                            label: "Channels"
                            value: convert.workspace.conversionModel.channels
                            chooser: convert.workspace.conversionModel.channelOptions.length > 1
                            onActivated: convert.workspace.conversionModel.next_channels()
                        }
                        Setting {
                            visible: convert.workspace.conversionModel.bitDepthOptions.length > 1
                            label: "Bit depth"
                            value: convert.workspace.conversionModel.bitDepth
                            chooser: true
                            onActivated: convert.workspace.conversionModel.next_bit_depth()
                        }
                        Setting {
                            visible: convert.formats.length > 0
                                && ["wav", "aiff"].indexOf(convert.formats[convert.formatIndex].id) >= 0
                                && convert.workspace.conversionModel.bitDepth !== "Keep source"
                            label: "Dither"
                            value: convert.workspace.conversionModel.dither ? "On" : "Off"
                            chooser: true
                            onActivated: convert.workspace.conversionModel.toggle_dither()
                        }
                        Setting {
                            label: "Metadata"
                            value: convert.workspace.conversionModel.copyMetadata
                                ? "Copy compatible tags"
                                : "Skip tags"
                            chooser: true
                            onActivated: convert.workspace.conversionModel.toggle_metadata()
                        }
                    }

                    TextButton {
                        width: parent.width
                        kind: "primary"
                        text: convert.workspace.conversionModel.hasPreview
                            ? (convert.workspace.conversionModel.previewExecutable ? "Start conversion" : "Review blocked preview")
                            : "Review conversion"
                        enabledAction: convert.inputs.length > 0 && convert.formats.length > 0
                        onClicked: convert.workspace.conversionModel.preview_or_start()
                    }

                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: convert.workspace.conversionModel.previewSummary
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
                text: convert.workspace.conversionModel.previewSummary
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

            TextButton {
                implicitHeight: 28
                kind: "ghost"
                text: "Cancel conversions"
                enabledAction: convert.workspace.conversionModel.canCancel
                onClicked: convert.workspace.conversionModel.cancel_all()
            }
            TextButton {
                implicitHeight: 28
                kind: "ghost"
                text: "Open output folder"
                enabledAction: true
                onClicked: convert.workspace.conversionModel.open_output_folder()
            }
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
