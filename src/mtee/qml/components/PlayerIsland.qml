import QtQuick
import Mtee

// Floating "music player island": track, transport with progress, then queue,
// volume and fullscreen. Visible while a track is loaded unless disabled.
Rectangle {
    id: island

    required property var workspace
    readonly property var player: workspace.playerModel
    readonly property var track: player.playingTrack
    readonly property bool fullscreen: workspace.fullscreen
    readonly property bool inPlaylist: track.id !== undefined
        && workspace.playlistsContaining(track.id, workspace.revision).length > 0

    objectName: "playerIsland"
    height: Theme.islandHeight
    color: Theme.surface
    border.width: 1
    border.color: Theme.separator

    function time(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const minutes = Math.floor(total / 60)
        const secs = total % 60
        return minutes + ":" + (secs < 10 ? "0" : "") + secs
    }

    // Swallow clicks so the list underneath never receives them.
    MouseArea { anchors.fill: parent }

    Item {
        id: left
        x: 12
        width: parent.width * 0.3
        height: parent.height

        CoverArt {
            id: cover
            objectName: "playerIslandCover"
            anchors.verticalCenter: parent.verticalCenter
            width: 48
            height: 48
            pattern: island.track.cover !== undefined ? island.track.cover : -1
            source: island.track.coverUrl || ""

            MouseArea {
                enabled: !island.fullscreen
                anchors.fill: parent
                cursorShape: island.fullscreen ? Qt.ArrowCursor : Qt.PointingHandCursor
                onClicked: island.workspace.setFullscreen(true)
            }
        }

        Column {
            id: identity
            anchors.left: cover.right
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(Math.max(titleText.implicitWidth, artistText.implicitWidth),
                            left.width - cover.width - 12 - addButton.width - 8)
            spacing: 2

            Text {
                id: titleText
                width: parent.width
                text: island.track.title || ""
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                id: artistText
                width: parent.width
                text: island.track.artist && island.track.artist.length > 0 ? island.track.artist : "Unknown artist"
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        IconButton {
            id: addButton
            anchors.left: identity.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            hoverBackground: false
            icon: island.inPlaylist ? "check" : "add-playlist"
            iconSize: 18
            iconColor: island.inPlaylist ? Theme.secondary : Theme.textSecondary
            hoverColor: Theme.secondary
            tip: "Add to playlist"
            onClicked: {
                playlistMenu.trackIds = [island.track.id]
                playlistMenu.popup(addButton, 0, -playlistMenu.implicitHeight)
            }
        }
    }

    Column {
        id: center
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width * 0.4
        spacing: 2

        TransportControls {
            anchors.horizontalCenter: parent.horizontalCenter
            player: island.player
        }

        Row {
            visible: island.player.status !== "Error"
            width: parent.width
            spacing: 8

            Text {
                width: 36
                horizontalAlignment: Text.AlignRight
                anchors.verticalCenter: parent.verticalCenter
                text: island.time(island.player.position)
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
                font.features: { "tnum": 1 }
            }

            LineSlider {
                objectName: "islandProgress"
                width: parent.width - 88
                anchors.verticalCenter: parent.verticalCenter
                from: 0
                enabled: island.player.seekable
                to: island.player.duration || island.track.seconds || 1
                value: island.player.position
                onMoved: (value) => island.player.seek(value)
            }

            Text {
                width: 36
                anchors.verticalCenter: parent.verticalCenter
                text: island.track.duration || "0:00"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
                font.features: { "tnum": 1 }
            }
        }

        Row {
            visible: island.player.status === "Error"
            width: parent.width
            spacing: 6

            Text {
                width: parent.width - retryButton.width - nextButton.width - 12
                text: island.player.errorMessage || "Playback failed."
                elide: Text.ElideRight
                color: Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
                anchors.verticalCenter: parent.verticalCenter
            }

            IconButton {
                id: retryButton
                width: 26
                height: 24
                icon: "play"
                iconSize: 14
                tip: "Retry"
                onClicked: island.player.retry()
            }

            IconButton {
                id: nextButton
                width: 26
                height: 24
                icon: "next"
                iconSize: 14
                tip: "Next"
                onClicked: island.player.next()
            }
        }
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            hoverBackground: false
            icon: "queue"
            iconSize: 18
            active: island.workspace.rightPanelVisible && island.workspace.rightPanelTab === "queue"
            tip: "Queue and history"
            onClicked: island.workspace.toggleRightPanel("queue")
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            hoverBackground: false
            icon: island.player.muted || island.player.volume === 0 ? "volume-off" : "volume"
            iconSize: 18
            tip: island.player.muted ? "Unmute" : "Mute"
            onClicked: island.player.toggleMute()
        }

        LineSlider {
            visible: island.width >= 760
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(96, Math.max(48, island.width * 0.08))
            from: 0
            to: 100
            value: island.player.muted ? 0 : island.player.volume
            onMoved: (value) => island.player.setVolume(Math.round(value))
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            hoverBackground: false
            objectName: "islandFullscreenButton"
            icon: island.fullscreen ? "exit-fullscreen" : "fullscreen"
            iconSize: 18
            tip: island.fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen player (F11)"
            onClicked: island.workspace.setFullscreen(!island.fullscreen)
        }
    }

    AddToPlaylistMenu {
        id: playlistMenu
        workspace: island.workspace
    }
}
