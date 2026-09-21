import QtQuick
import Mtee

Panel {
    id: convert

    objectName: "convertView"
    property var workspace
    property bool advancedOpen: false
    property bool started: false

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacingLarge
        spacing: Theme.spacing

        Row {
            width: parent.width
            height: 38

            Column {
                width: parent.width - actions.width - Theme.spacing
                spacing: 2
                Text {
                    text: "Convert"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeTitle
                }
                Text {
                    text: "Prepare copies while keeping the source files untouched"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            Row {
                id: actions
                spacing: Theme.spacingSmall
                ToolButton { text: "Add files"; enabledAction: false }
                ToolButton { text: "Add selected tracks"; enabledAction: false }
            }
        }

        Row {
            width: parent.width
            height: parent.height - 38 - Theme.spacing
            spacing: Theme.spacing

            Panel {
                width: parent.width * 0.56
                height: parent.height

                SectionLabel {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.margins: Theme.spacing
                    text: "Input files  ·  2 selected"
                }

                ListView {
                    anchors.top: parent.top
                    anchors.topMargin: 42
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: Theme.spacing
                    clip: true
                    model: workspace.tracks.slice(0, 2)

                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: 78
                        radius: Theme.controlRadius
                        color: index === 1 && workspace.conversionError ? Qt.rgba(1, 0.35, 0.3, 0.08) : Theme.background
                        border.width: 1
                        border.color: index === 1 && workspace.conversionError ? Theme.danger : Theme.border

                        Column {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: Theme.spacing
                            spacing: 3
                            Text { text: modelData.filename; color: Theme.textPrimary; elide: Text.ElideRight; width: parent.width; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody }
                            Text { text: modelData.format + "  ·  " + modelData.duration; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                            Text { text: index === 1 && workspace.conversionError ? "Could not convert · Retry available" : (convert.started ? "Ready · 100%" : "Ready to convert"); color: index === 1 && workspace.conversionError ? Theme.danger : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        }
                    }
                }
            }

            Panel {
                width: parent.width * 0.44 - Theme.spacing
                height: parent.height

                SectionLabel {
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.margins: Theme.spacing
                    text: "Output format"
                }

                Column {
                    anchors.top: parent.top
                    anchors.topMargin: 42
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: Theme.spacing
                    spacing: Theme.spacing

                    Text { text: "Format"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                    Rectangle { width: parent.width; height: 36; radius: Theme.controlRadius; color: Theme.activeSurface; border.width: 1; border.color: Theme.accent; Text { anchors.left: parent.left; anchors.leftMargin: Theme.spacing; anchors.verticalCenter: parent.verticalCenter; text: "MP3"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody } Text { anchors.right: parent.right; anchors.rightMargin: Theme.spacing; anchors.verticalCenter: parent.verticalCenter; text: "⌄"; color: Theme.textSecondary; font.pixelSize: 16 } }

                    Text { text: "Quality"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                    Rectangle { width: parent.width; height: 36; radius: Theme.controlRadius; color: Theme.background; border.width: 1; border.color: Theme.border; Text { anchors.left: parent.left; anchors.leftMargin: Theme.spacing; anchors.verticalCenter: parent.verticalCenter; text: "320 kbps · CBR"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody } }

                    Text { text: "Output folder"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                    Rectangle { width: parent.width; height: 36; radius: Theme.controlRadius; color: Theme.background; border.width: 1; border.color: Theme.border; Text { anchors.left: parent.left; anchors.leftMargin: Theme.spacing; anchors.verticalCenter: parent.verticalCenter; text: "Converted / MP3"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody; elide: Text.ElideRight; width: parent.width - 24 } }

                    ToolButton { text: convert.advancedOpen ? "Hide Advanced" : "Advanced"; onClicked: convert.advancedOpen = !convert.advancedOpen }

                    Column {
                        visible: convert.advancedOpen
                        spacing: Theme.spacingSmall
                        Text { text: "Sample rate  44.1 kHz"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        Text { text: "Channels  Stereo"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        Text { text: "Metadata  Copy compatible tags"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                    }

                    ToolButton {
                        text: "Start conversion"
                        primary: true
                        onClicked: convert.started = true
                    }

                    Text {
                        visible: workspace.conversionError
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "One output could not be created. The source is safe. Retry this item after checking the output folder."
                        color: Theme.danger
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    Row {
                        visible: workspace.conversionError
                        spacing: Theme.spacingSmall
                        ToolButton { text: "Retry"; onClicked: workspace.retryConversion() }
                        ToolButton { text: "Open output folder"; enabledAction: false }
                    }
                }
            }
        }
    }
}
