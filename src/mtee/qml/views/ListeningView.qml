import QtQuick
import Mtee
import "../components"

Panel {
    id: listening

    objectName: "listeningView"
    property var workspace
    property bool playing: true
    property real progress: 0.32
    focus: true
    activeFocusOnTab: true

    Keys.onSpacePressed: {
        if (!event.isAutoRepeat) {
            playing = !playing
            event.accepted = true
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacingLarge
        spacing: Theme.spacing

        Row {
            width: parent.width
            height: 32

            Column {
                width: parent.width - backButton.width - Theme.spacing
                spacing: 2
                Text {
                    text: "Listening view"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeTitle
                }
                Text {
                    text: "The played track stays independent from the current selection"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            ToolButton {
                id: backButton
                text: "Back to browser"
                onClicked: workspace.setScreen("browser")
            }
        }

        Row {
            width: parent.width
            height: parent.height - 32 - Theme.spacing
            spacing: Theme.spacingLarge

            Column {
                width: parent.width - inspector.width - Theme.spacingLarge
                height: parent.height
                spacing: Theme.spacingLarge

                Row {
                    width: parent.width
                    height: Math.min(290, parent.height * 0.44)
                    spacing: Theme.spacingLarge

                    Rectangle {
                        width: height
                        height: parent.height
                        radius: Theme.panelRadius
                        color: Theme.activeSurface
                        border.width: 1
                        border.color: Theme.border

                        Text {
                            anchors.centerIn: parent
                            text: workspace.noArtwork ? "No artwork" : "Artwork preview"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }
                    }

                    Column {
                        width: parent.width - parent.children[0].width - Theme.spacingLarge
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.spacingSmall

                        Text {
                            text: "Carrier Wave"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: 30
                        }
                        Text {
                            text: "Loop Foundry"
                            color: Theme.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }
                        Text {
                            text: "Techno   ·   134 BPM   ·   5A   ·   FLAC"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }
                        Text {
                            text: "Now playing"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }
                }

                Panel {
                    width: parent.width
                    height: 116

                    SectionLabel {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.margins: Theme.spacing
                        text: "Playback"
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.topMargin: 47
                        anchors.leftMargin: Theme.spacing
                        anchors.rightMargin: Theme.spacing
                        height: 8
                        radius: 4
                        color: Theme.activeSurface

                        Rectangle {
                            width: parent.width * listening.progress
                            height: parent.height
                            radius: parent.radius
                            color: Theme.accent
                        }
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.spacing
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: Theme.spacing
                        text: "2:18"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.spacing
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: Theme.spacing
                        text: "7:12"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }

                Row {
                    width: parent.width
                    height: 34
                    spacing: Theme.spacingSmall

                    Item { width: Math.max(0, (parent.width - controls.width) / 2); height: 1 }
                    Row {
                        id: controls
                        spacing: Theme.spacingSmall
                        ToolButton { text: "Previous"; enabledAction: false }
                        ToolButton { text: listening.playing ? "Pause" : "Play"; primary: true; onClicked: listening.playing = !listening.playing }
                        ToolButton { text: "Next"; enabledAction: false }
                    }
                    Item { width: Math.max(0, (parent.width - controls.width) / 2); height: 1 }
                }

                Panel {
                    width: parent.width
                    height: Math.max(130, parent.height - 520)

                    SectionLabel {
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.margins: Theme.spacing
                        text: "Queue  ·  order captured at launch"
                    }

                    ListView {
                        anchors.top: parent.top
                        anchors.topMargin: 38
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: Theme.spacing
                        model: workspace.queue
                        delegate: Row {
                            required property var modelData
                            width: parent.width
                            height: 30
                            spacing: Theme.spacing
                            Text { text: modelData.position; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; width: 25 }
                            Text { text: modelData.title; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody; width: parent.width * 0.55; elide: Text.ElideRight }
                            Text { text: modelData.artist; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; elide: Text.ElideRight }
                        }
                    }
                }
            }

            MetadataInspector {
                id: inspector
                width: Math.min(330, parent.width * 0.34)
                height: parent.height
                workspace: listening.workspace
                onCloseRequested: listening.workspace.setScreen("browser")
            }
        }
    }
}
