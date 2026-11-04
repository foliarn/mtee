import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The player, full width in the footer of the frame (decision U11, plan 131.8): the track on the
// left, transport and seek bar in the middle, then queue, volume and fullscreen. It is always
// shown. With nothing playing it greys out and the transport, seek and volume are disabled.
// Below 1100 px the volume is an icon with a popup slider; below 760 px queue, fullscreen and
// like move into a "more" menu.
Rectangle {
    id: bar

    required property var workspace
    // Bumped on every layout change, so the queue button is read again.
    property int layoutRevision: 0
    Connections {
        target: bar.workspace
        function onLayoutChanged() { bar.layoutRevision++ }
    }
    readonly property bool queueShown: {
        layoutRevision
        const side = workspace.toolWindows.sideOf("queue")
        if (side.length === 0)
            return false
        const dock = workspace.dockState(side)
        return dock.open === true && dock.windows.indexOf("queue") >= 0
    }
    readonly property var player: workspace.playerModel
    readonly property var track: player.playingTrack
    // An empty track dictionary means nothing is playing.
    readonly property bool hasTrack: track.id !== undefined
    readonly property bool fullscreen: workspace.fullscreen
    readonly property bool compactVolume: width < Theme.overlayDockWidth
    readonly property bool compactActions: width < Theme.singleWindowWidth
    readonly property bool inPlaylist: hasTrack
        && workspace.playlistsContaining(track.id, workspace.revision).length > 0
    // Confirmed artists of the playing track; re-read when the library revision changes.
    readonly property var artists: {
        workspace.revision
        return hasTrack && typeof workspace.trackArtists === "function"
            ? workspace.trackArtists(track.id) : []
    }
    readonly property bool liked: hasTrack && workspace.revision >= 0
        && typeof workspace.isLiked === "function" && workspace.isLiked(track.id)

    // The name the tests look for. Kept from the floating island, which this bar replaces.
    objectName: "playerIsland"
    height: Theme.playerBarHeight
    color: Theme.chrome

    function time(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const minutes = Math.floor(total / 60)
        const secs = total % 60
        return minutes + ":" + (secs < 10 ? "0" : "") + secs
    }

    // The library ids of the playing track: what a playlist can take.
    readonly property var dragIds: {
        if (!hasTrack)
            return []
        const ids = typeof workspace.localTrackIds === "function"
            ? workspace.localTrackIds([track.id]) : [track.id]
        return Array.from(ids).filter(identity => String(identity).length > 0)
    }
    property bool dragging: false
    property point dragPoint: Qt.point(0, 0)

    // The same menu as a track row, for the playing track.
    function openTrackMenu(anchor, x, y) {
        if (!hasTrack)
            return
        trackMenu.trackId = String(track.id)
        trackMenu.trackIds = [String(track.id)]
        trackMenu.orderedIds = [String(track.id)]
        trackMenu.source = String(player.playingSource || "")
        trackMenu.captureQueueTargets()
        trackMenu.prepare(true)
        trackMenu.popup(anchor, x, y - trackMenu.implicitHeight)
    }

    TrackMenu {
        id: trackMenu
        objectName: "playerTrackMenu"
        workspace: bar.workspace
        listKind: "playing"
    }

    TrackDragPreview {
        parent: Overlay.overlay
        visible: bar.dragging
        trackTitle: String(bar.track.title || "")
        artist: String(bar.track.artist || "")
        count: 1
        readonly property point pointer: Overlay.overlay ? Overlay.overlay.mapFromItem(null, bar.dragPoint.x, bar.dragPoint.y) : Qt.point(0, 0)
        x: Math.max(8, Math.min(parent.width - width - 8, pointer.x + 16))
        y: Math.max(8, Math.min(parent.height - height - 8, pointer.y + 16))
    }

    Item {
        id: dragSession
        objectName: "playerDragSession"
        parent: Overlay.overlay
        width: 1; height: 1
        readonly property point pointer: Overlay.overlay ? Overlay.overlay.mapFromItem(null, bar.dragPoint.x, bar.dragPoint.y) : Qt.point(0, 0)
        x: pointer.x; y: pointer.y
        property var dragTrackIds: bar.dragIds
        property var dragEntryIds: []
        property string dragSource: String(bar.player.playingSource || "")
        property int dragVersion: -1
        property bool dragCanAdd: bar.dragIds.length > 0
        Drag.active: bar.dragging
        Drag.source: dragSession
        Drag.keys: ["mtee-tracks"]
        Drag.supportedActions: Qt.CopyAction
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
            pattern: bar.track.cover !== undefined ? bar.track.cover : -1
            source: bar.track.coverUrl || ""

            MouseArea {
                enabled: !bar.fullscreen
                anchors.fill: parent
                cursorShape: bar.fullscreen ? Qt.ArrowCursor : Qt.PointingHandCursor
                onClicked: bar.workspace.setFullscreen(true)
            }
        }

        Column {
            id: identity
            anchors.left: cover.right
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            // Natural width of the artist line: the links row, or the plain text.
            readonly property real artistNaturalWidth: artistRow.visible
                ? artistRow.childrenRect.width : artistText.implicitWidth
            width: Math.max(0, Math.min(Math.max(titleText.implicitWidth, artistNaturalWidth),
                            left.width - cover.width - 12 - addButton.width - likeButton.width - 8))
            spacing: 2

            // Opens the playlist, folder or artist page the track plays from. With nothing
            // playing the title is a muted placeholder.
            Text {
                id: titleText
                width: parent.width
                text: bar.hasTrack ? (bar.track.title || "") : "Nothing playing"
                elide: Text.ElideRight
                color: bar.hasTrack ? Theme.textPrimary : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
                font.underline: bar.hasTrack && titleMouse.containsMouse

                MouseArea {
                    id: titleMouse
                    objectName: "playerIslandTitle"
                    anchors.fill: parent
                    enabled: bar.hasTrack
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: bar.workspace.revealTrack(bar.track.id, bar.player.playingSource)
                }

                // The same menu as a track row, for the playing track.
                TapHandler {
                    objectName: "playerTitleMenuTap"
                    acceptedButtons: Qt.RightButton
                    enabled: bar.hasTrack
                    onTapped: (point) => bar.openTrackMenu(titleText, point.position.x, point.position.y)
                }

                // Dragging the title onto a playlist (sidebar row or open tab) adds the track,
                // with the same keys and fields as a track row of a list.
                DragHandler {
                    id: titleDrag
                    objectName: "playerTitleDrag"
                    target: null
                    acceptedButtons: Qt.LeftButton
                    enabled: bar.hasTrack && bar.dragIds.length > 0
                    onActiveChanged: {
                        if (!active && bar.dragging)
                            dragSession.Drag.drop()
                        bar.dragging = active
                    }
                    onCentroidChanged: bar.dragPoint = titleText.mapToItem(null, centroid.position.x, centroid.position.y)
                }
            }

            // Each confirmed artist is its own link, separated by commas.
            Row {
                id: artistRow
                objectName: "playerIslandArtists"
                visible: bar.artists.length > 0
                width: parent.width
                height: childrenRect.height
                clip: true

                Repeater {
                    model: bar.artists

                    Row {
                        id: artistEntry
                        required property var modelData
                        required property int index

                        Text {
                            id: artistName
                            objectName: "playerIslandArtist_" + artistEntry.index
                            text: artistEntry.modelData.name
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                            font.underline: artistMouse.containsMouse

                            MouseArea {
                                id: artistMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: bar.workspace.openArtistPage(
                                    artistEntry.modelData.id, artistEntry.modelData.name)
                            }
                        }

                        Text {
                            visible: artistEntry.index < bar.artists.length - 1
                            text: ", "
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }
                }
            }

            // Plain artist tag, or "Unknown artist", when there are no confirmed artists.
            Text {
                id: artistText
                objectName: "playerIslandArtistText"
                visible: bar.artists.length === 0 && bar.hasTrack
                width: parent.width
                text: bar.track.artist && bar.track.artist.length > 0 ? bar.track.artist : "Unknown artist"
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
            enabledAction: bar.hasTrack
            icon: bar.inPlaylist ? "check" : "add-playlist"
            iconSize: 18
            iconColor: bar.inPlaylist ? Theme.secondary : Theme.textSecondary
            hoverColor: Theme.secondary
            tip: "Add to playlist"
            onClicked: {
                playlistMenu.trackIds = [bar.track.id]
                playlistMenu.popup(addButton, 0, -playlistMenu.implicitHeight)
            }
        }

        IconButton {
            id: likeButton
            objectName: "playerIslandLike"
            anchors.left: addButton.right
            anchors.verticalCenter: parent.verticalCenter
            visible: bar.hasTrack && !bar.compactActions && typeof bar.workspace.toggleLike === "function"
            hoverBackground: false
            icon: bar.liked ? "heart-filled" : "heart"
            iconSize: 18
            iconColor: bar.liked ? Theme.secondary : Theme.textSecondary
            hoverColor: bar.liked ? Theme.secondary : Theme.textPrimary
            tip: "Like track"
            onClicked: bar.workspace.toggleLike(bar.track.id)
        }
    }

    // Transport and seek bar: disabled and greyed while nothing plays.
    Column {
        id: center
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(720, Math.max(320, parent.width * 0.5))
        spacing: 2
        enabled: bar.hasTrack
        opacity: bar.hasTrack ? 1.0 : 0.4

        TransportControls {
            anchors.horizontalCenter: parent.horizontalCenter
            player: bar.player
            buttonSize: 36
            iconSize: 22
            playSize: 40
        }

        Row {
            visible: bar.player.status !== "Error"
            width: parent.width
            spacing: 8

            Text {
                width: 44
                horizontalAlignment: Text.AlignRight
                anchors.verticalCenter: parent.verticalCenter
                text: bar.time(bar.player.position)
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
                enabled: bar.player.seekable
                to: bar.player.duration || bar.track.seconds || 1
                value: bar.player.position
                onMoved: (value) => bar.player.seek(value)
            }

            Text {
                width: 44
                anchors.verticalCenter: parent.verticalCenter
                text: bar.track.duration || "0:00"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.features: { "tnum": 1 }
            }
        }

        Row {
            visible: bar.player.status === "Error"
            width: parent.width
            spacing: 6

            Text {
                width: parent.width - retryButton.width - nextButton.width - 12
                text: bar.player.errorMessage || "Playback failed."
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
                onClicked: bar.player.retry()
            }

            IconButton {
                id: nextButton
                width: 26
                height: 24
                icon: "next"
                iconSize: 14
                tip: "Next"
                onClicked: bar.player.next()
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
            visible: !bar.compactActions
            hoverBackground: false
            icon: "queue"
            iconSize: 18
            objectName: "islandQueueButton"
            active: bar.fullscreen ? bar.workspace.fullscreenPage === 1 : bar.queueShown
            tip: bar.fullscreen ? "Queue and track details" : "Queue and history"
            onClicked: {
                if (bar.fullscreen)
                    bar.workspace.setFullscreenPage(bar.workspace.fullscreenPage === 1 ? 0 : 1)
                else
                    bar.workspace.toggleToolWindow("queue")
            }
        }

        IconButton {
            id: moreButton
            objectName: "playerMoreButton"
            anchors.verticalCenter: parent.verticalCenter
            visible: bar.compactActions
            hoverBackground: false
            icon: "more"
            iconSize: 18
            tip: "More"
            onClicked: moreMenu.toggle()
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            visible: !bar.compactVolume
            enabledAction: bar.hasTrack
            hoverBackground: false
            icon: bar.player.muted || bar.player.volume === 0 ? "volume-off" : "volume"
            iconSize: 18
            tip: bar.player.muted ? "Unmute" : "Mute"
            onClicked: bar.player.toggleMute()
        }

        LineSlider {
            visible: !bar.compactVolume
            enabled: bar.hasTrack
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(96, Math.max(48, bar.width * 0.08))
            from: 0
            to: 100
            value: bar.player.muted ? 0 : bar.player.volume
            onMoved: (value) => bar.player.setVolume(Math.round(value))
        }

        // Below 1100 px the volume is an icon; its popup holds the mute button and the slider.
        IconButton {
            id: volumeButton
            objectName: "playerVolumeButton"
            anchors.verticalCenter: parent.verticalCenter
            visible: bar.compactVolume
            enabledAction: bar.hasTrack
            hoverBackground: false
            icon: bar.player.muted || bar.player.volume === 0 ? "volume-off" : "volume"
            iconSize: 18
            tip: "Volume"
            onClicked: volumePopover.toggle()
        }

        IconButton {
            anchors.verticalCenter: parent.verticalCenter
            visible: !bar.compactActions
            hoverBackground: false
            objectName: "islandFullscreenButton"
            icon: bar.fullscreen ? "exit-fullscreen" : "fullscreen"
            iconSize: 18
            tip: bar.fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen player (F11)"
            onClicked: bar.workspace.setFullscreen(!bar.fullscreen)
        }
    }

    // Below 1100 px: the volume icon's popup, with the mute button and the slider.
    Popover {
        id: volumePopover
        objectName: "playerVolumePopover"
        anchorItem: volumeButton
        bodyWidth: 220

        Row {
            width: volumePopover.bodyWidth
            height: 32
            spacing: 8

            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                hoverBackground: false
                icon: bar.player.muted || bar.player.volume === 0 ? "volume-off" : "volume"
                iconSize: 18
                tip: bar.player.muted ? "Unmute" : "Mute"
                onClicked: bar.player.toggleMute()
            }

            LineSlider {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 44
                from: 0
                to: 100
                value: bar.player.muted ? 0 : bar.player.volume
                onMoved: (value) => bar.player.setVolume(Math.round(value))
            }
        }
    }

    // Below 760 px: like, queue and fullscreen, moved out of the bar.
    Popover {
        id: moreMenu
        objectName: "playerMoreMenu"
        anchorItem: moreButton
        bodyWidth: 200

        Column {
            width: moreMenu.bodyWidth
            spacing: 2

            PlayerMenuRow {
                objectName: "playerMoreLike"
                width: parent.width
                visible: bar.hasTrack
                icon: bar.liked ? "heart-filled" : "heart"
                active: bar.liked
                label: bar.liked ? "Unlike track" : "Like track"
                onTriggered: {
                    moreMenu.close()
                    bar.workspace.toggleLike(bar.track.id)
                }
            }

            PlayerMenuRow {
                objectName: "playerMoreQueue"
                width: parent.width
                icon: "queue"
                active: bar.fullscreen ? bar.workspace.fullscreenPage === 1 : bar.queueShown
                label: bar.fullscreen ? "Queue and track details" : "Queue and history"
                onTriggered: {
                    moreMenu.close()
                    if (bar.fullscreen)
                        bar.workspace.setFullscreenPage(bar.workspace.fullscreenPage === 1 ? 0 : 1)
                    else
                        bar.workspace.toggleToolWindow("queue")
                }
            }

            PlayerMenuRow {
                objectName: "playerMoreFullscreen"
                width: parent.width
                icon: bar.fullscreen ? "exit-fullscreen" : "fullscreen"
                label: bar.fullscreen ? "Exit fullscreen" : "Fullscreen player"
                onTriggered: {
                    moreMenu.close()
                    bar.workspace.setFullscreen(!bar.fullscreen)
                }
            }
        }
    }

    AddToPlaylistMenu {
        id: playlistMenu
        workspace: bar.workspace
    }
}
