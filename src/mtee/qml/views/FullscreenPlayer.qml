import QtQuick
import Mtee
import "../components"

// Fullscreen player: source at the top, large cover and identity, waveform
// placeholder and transport. It follows the playing track, not the selection.
Rectangle {
    id: player

    required property var workspace
    readonly property var track: workspace.playingTrack
    readonly property real duration: track.seconds || 1

    objectName: "fullscreenPlayer"
    color: Theme.editor

    function time(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const minutes = Math.floor(total / 60)
        const secs = total % 60
        return minutes + ":" + (secs < 10 ? "0" : "") + secs
    }

    Item {
        id: top
        width: parent.width
        height: 64

        Column {
            x: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            SectionLabel {
                text: "Playing from " + (player.workspace.playingSourceKind === "playlist" ? "playlist" : "folder")
            }

            Text {
                text: player.workspace.playingSourceTitle
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            IconButton {
                icon: "queue"
                iconSize: 18
                tip: "Queue and history"
                onClicked: {
                    player.workspace.setFullscreen(false)
                    player.workspace.showRightPanel("queue")
                }
            }

            IconButton {
                objectName: "exitFullscreen"
                icon: "exit-fullscreen"
                iconSize: 18
                tip: "Exit fullscreen (Esc)"
                onClicked: player.workspace.setFullscreen(false)
            }
        }
    }

    Column {
        id: stage
        anchors.top: top.bottom
        anchors.bottom: bottom.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 96, 960)

        readonly property int coverSize: Math.max(120, Math.min(380, height - 150))

        topPadding: Math.max(0, (height - coverSize - 110) / 2)
        spacing: 18

        CoverArt {
            anchors.horizontalCenter: parent.horizontalCenter
            width: stage.coverSize
            height: stage.coverSize
            pattern: player.track.cover !== undefined ? player.track.cover : -1
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            spacing: 6

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: player.track.title || ""
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: 32
                font.weight: Font.Bold
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: player.track.artist && player.track.artist.length > 0 ? player.track.artist : "Unknown artist"
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 16
            }
        }
    }

    Column {
        id: bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 32
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 96, 960)
        spacing: 12

        WaveformPreview {
            objectName: "waveformPreview"
            width: parent.width
            height: 72
            seed: player.track.id || ""
            ratio: player.workspace.position / player.duration
            onSeekRequested: (ratio) => player.workspace.seek(ratio * player.duration)
        }

        Item {
            width: parent.width
            height: 16

            Text {
                text: player.time(player.workspace.position)
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.features: { "tnum": 1 }
            }

            Text {
                anchors.right: parent.right
                text: player.track.duration || "0:00"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.features: { "tnum": 1 }
            }
        }

        Item {
            width: parent.width
            height: 56

            TransportControls {
                anchors.centerIn: parent
                workspace: player.workspace
                spacing: 20
                buttonSize: 40
                iconSize: 22
                playSize: 56
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    hoverBackground: false
                    icon: player.workspace.muted || player.workspace.volume === 0 ? "volume-off" : "volume"
                    iconSize: 20
                    tip: player.workspace.muted ? "Unmute" : "Mute"
                    onClicked: player.workspace.toggleMute()
                }

                LineSlider {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 110
                    from: 0
                    to: 100
                    value: player.workspace.muted ? 0 : player.workspace.volume
                    onMoved: (value) => player.workspace.setVolume(Math.round(value))
                }
            }
        }
    }
}
