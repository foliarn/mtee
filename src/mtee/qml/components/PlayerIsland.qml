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
    // Confirmed artists of the playing track; re-read when the library revision changes.
    readonly property var artists: {
        workspace.revision
        return track.id !== undefined && typeof workspace.trackArtists === "function"
            ? workspace.trackArtists(track.id) : []
    }
    readonly property bool liked: track.id !== undefined && workspace.revision >= 0
        && typeof workspace.isLiked === "function" && workspace.isLiked(track.id)

    objectName: "playerIsland"
    height: Theme.islandHeight
    color: Theme.chrome

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.separator
    }

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
        x: 16
        width: Math.max(0, (parent.width - center.width) / 2 - 32)
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
            width: Math.max(0, Math.min(Math.max(titleText.implicitWidth, artistText.implicitWidth),
                            left.width - cover.width - 12 - addButton.width - likeButton.width - 8))
            spacing: 2

            // Opens the playlist, folder or artist page the track plays from.
            Text {
                id: titleText
                width: parent.width
                text: island.track.title || ""
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
                font.underline: titleMouse.containsMouse

                MouseArea {
                    id: titleMouse
                    objectName: "playerIslandTitle"
                    anchors.fill: parent
                    enabled: island.track.id !== undefined
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: island.workspace.revealTrack(island.track.id, island.player.playingSource)
                }
            }

            // A link only when the track has confirmed artists; several open a small menu.
            Text {
                id: artistText
                readonly property bool linked: island.artists.length > 0
                width: parent.width
                text: island.track.artist && island.track.artist.length > 0 ? island.track.artist : "Unknown artist"
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.underline: artistMouse.containsMouse

                MouseArea {
                    id: artistMouse
                    objectName: "playerIslandArtist"
                    anchors.fill: parent
                    enabled: artistText.linked
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (island.artists.length === 1)
                            island.workspace.openArtistPage(island.artists[0].id, island.artists[0].name)
                        else
                            artistMenu.popup(artistText, 0, -artistMenu.implicitHeight)
                    }
                }
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

        IconButton {
            id: likeButton
            objectName: "playerIslandLike"
            anchors.left: addButton.right
            anchors.verticalCenter: parent.verticalCenter
            visible: island.track.id !== undefined && typeof island.workspace.toggleLike === "function"
            hoverBackground: false
            icon: island.liked ? "heart-filled" : "heart"
            iconSize: 18
            iconColor: island.liked ? Theme.secondary : Theme.textSecondary
            hoverColor: island.liked ? Theme.secondary : Theme.textPrimary
            tip: "Like track"
            onClicked: island.workspace.toggleLike(island.track.id)
        }
    }

    Column {
        id: center
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(720, Math.max(320, parent.width * 0.5))
        spacing: 2

        TransportControls {
            anchors.horizontalCenter: parent.horizontalCenter
            player: island.player
            buttonSize: 36
            iconSize: 22
            playSize: 40
        }

        Row {
            visible: island.player.status !== "Error"
            width: parent.width
            spacing: 8

            Text {
                width: 44
                horizontalAlignment: Text.AlignRight
                anchors.verticalCenter: parent.verticalCenter
                text: island.time(island.player.position)
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.features: { "tnum": 1 }
            }

            LineSlider {
                objectName: "islandProgress"
                width: parent.width - 104
                anchors.verticalCenter: parent.verticalCenter
                from: 0
                enabled: island.player.seekable
                to: island.player.duration || island.track.seconds || 1
                value: island.player.position
                onMoved: (value) => island.player.seek(value)
            }

            Text {
                width: 44
                anchors.verticalCenter: parent.verticalCenter
                text: island.track.duration || "0:00"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
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
        anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            hoverBackground: false
            icon: "queue"
            iconSize: 18
            objectName: "islandQueueButton"
            active: island.fullscreen ? island.workspace.fullscreenPage === 1
                : island.workspace.rightPanelVisible && island.workspace.rightPanelTab === "queue"
            tip: island.fullscreen ? "Queue and track details" : "Queue and history"
            onClicked: {
                if (island.fullscreen)
                    island.workspace.setFullscreenPage(island.workspace.fullscreenPage === 1 ? 0 : 1)
                else
                    island.workspace.toggleRightPanel("queue")
            }
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

    AppMenu {
        id: artistMenu
        objectName: "playerIslandArtistMenu"

        Repeater {
            model: island.artists

            AppMenuItem {
                required property var modelData
                text: modelData.name
                onTriggered: island.workspace.openArtistPage(modelData.id, modelData.name)
            }
        }
    }
}
