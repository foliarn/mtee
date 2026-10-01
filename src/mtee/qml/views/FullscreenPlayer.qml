import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import Mtee
import "../components"

// Fullscreen player (plan 100): one rounded card tinted by the cover, with the track,
// its waveform, Play, like / playlist / more actions and the cover. It follows the
// playing track, not the selection; the floating island stays visible above it.
Rectangle {
    id: player

    required property var workspace
    readonly property var playback: workspace.playerModel
    readonly property var waveform: playback.waveformModel
    readonly property var accent: playback.accent
    readonly property var track: playback.playingTrack
    readonly property bool hasTrack: playback.playingId.length > 0
    readonly property bool liked: workspace.revision >= 0
        && typeof workspace.isLiked === "function" && workspace.isLiked(playback.playingId)
    readonly property bool inPlaylist: hasTrack
        && workspace.playlistsContaining(playback.playingId, workspace.revision).length > 0
    readonly property bool willPlay: playback.isPlaying
        || (playback.status === "Loading" && !playback.pausePending)
    readonly property real reserve: Theme.islandHeight + 2 * Theme.islandMargin
    readonly property real sideMargin: Math.max(48, width * 0.06)
    readonly property real cardWidth: Math.min(Theme.fsCardMaxWidth, width - 2 * sideMargin)
    readonly property bool coverVisible: cardWidth >= Theme.fsCoverHideWidth
    // The extra height is capped so the card never runs into the island.
    readonly property real baseInner: identity.implicitHeight + Theme.waveHeight + Theme.fsPlaySize + 40
    readonly property real extraHeight: Math.max(0, Math.min(Theme.fsCardExtra,
        height - reserve - Theme.fsTopBlock - 8 - (baseInner + 2 * Theme.fsCardPadding)))
    readonly property real innerHeight: leftColumn.implicitHeight
    readonly property real cardHeight: innerHeight + 2 * Theme.fsCardPadding
    readonly property bool hasAccent: accent.hasAccent
    readonly property color accentBase: hasAccent ? accent.baseColor : Theme.fsFallbackCard
    readonly property color accentDark: hasAccent ? accent.darkColor : Theme.fsFallbackCard
    property color shownBase: accentBase
    property color shownDark: accentDark

    readonly property int page: workspace.fullscreenPage
    readonly property real cardBottom: cardHolder.y + cardHolder.height
    // How far the card moves up so that only ``fsPeek`` of it stays visible on page 2.
    readonly property real maxOffset: Math.max(0, cardBottom - Theme.fsPeek - Theme.fsTopMargin)
    readonly property real page2Height: Math.max(0, height - Theme.fsPeek - Theme.fsTopMargin - reserve)
    // 0 on page 1, 1 on page 2, animated; the layers are placed from it, so the view is
    // never left between two pages.
    property real progress: 0
    property bool wheelLocked: false
    property real wheelAccum: 0

    objectName: "fullscreenPlayer"
    color: Theme.editor
    clip: true  // the layers scroll past the edges and must not draw over the title bar

    function syncProgress(animated) {
        const target = page === 1 ? 1 : 0
        pageAnimation.stop()
        if (animated && visible) {
            pageAnimation.to = target
            pageAnimation.start()
        } else {
            progress = target
        }
    }

    onPageChanged: syncProgress(true)
    onVisibleChanged: if (!visible) syncProgress(false)

    NumberAnimation {
        id: pageAnimation
        target: player
        property: "progress"
        duration: Theme.fsPageDuration
        easing.type: Easing.OutCubic
    }

    // One notch changes page; further events are ignored until the animation is over
    // and the inertia of the wheel or trackpad has faded.
    Timer {
        id: wheelUnlock
        interval: Theme.fsPageDuration + Theme.fsPageCooldown
        onTriggered: player.wheelLocked = false
    }

    Timer {
        id: wheelIdle
        interval: 300
        onTriggered: player.wheelAccum = 0
    }

    function handleWheel(wheel) {
        if (!hasTrack || wheelLocked)
            return
        const pixel = wheel.pixelDelta.y !== 0
        wheelAccum += pixel ? wheel.pixelDelta.y : wheel.angleDelta.y
        wheelIdle.restart()
        const threshold = pixel ? Theme.fsWheelPixelThreshold : Theme.fsWheelThreshold
        if (Math.abs(wheelAccum) < threshold)
            return
        const target = wheelAccum < 0 ? 1 : 0
        wheelAccum = 0
        if (target !== page) {
            wheelLocked = true
            wheelUnlock.restart()
            workspace.setFullscreenPage(target)
        }
    }

    // Wheel events that no child consumes (the Queue list will) change page.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: (wheel) => player.handleWheel(wheel)
    }

    Behavior on shownBase { ColorAnimation { duration: Theme.fsAccentFade } }
    Behavior on shownDark { ColorAnimation { duration: Theme.fsAccentFade } }

    Text {
        objectName: "fullscreenEmpty"
        visible: !player.hasTrack
        anchors.centerIn: parent
        text: "Play a track"
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: 16
    }

    // Page 1: moves up by ``maxOffset`` while ``progress`` goes from 0 to 1.
    Item {
        id: pages
        objectName: "fullscreenPages"
        y: -player.progress * player.maxOffset
        width: parent.width
        height: parent.height

        // Source of the queue: only its name is a link.
        Column {
            visible: player.hasTrack
            x: 24
            y: 14
            spacing: 2

            SectionLabel {
                text: "Playing from " + (player.playback.playingSourceKind === "playlist" ? "playlist" : "folder")
            }

            Text {
                objectName: "fullscreenSource"
                text: player.playback.playingSourceTitle
                color: sourceMouse.containsMouse ? Theme.primary : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
                font.underline: sourceMouse.containsMouse

                MouseArea {
                    id: sourceMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: player.workspace.openPlayingSource()
                }
            }
        }

        Item {
            id: cardHolder
            objectName: "fullscreenCard"
            visible: player.hasTrack
            x: (player.width - width) / 2
            y: Theme.fsTopBlock
                + Math.max(0, (player.height - player.reserve - Theme.fsTopBlock - height) / 2)
            width: player.cardWidth
            height: player.cardHeight

            // Discreet shadow, only for the grey card without an accent colour.
            Repeater {
                model: 6

                Rectangle {
                    required property int index
                    visible: !player.hasAccent
                    x: -(index + 1) * 4
                    y: -(index + 1) * 2 + 4
                    width: parent.width + (index + 1) * 8
                    height: parent.height + (index + 1) * 4
                    radius: Theme.fsCardRadius + (index + 1) * 4
                    color: "#000000"
                    opacity: Theme.fsShadowOpacity / 6
                }
            }

            Rectangle {
                anchors.fill: parent
                radius: Theme.fsCardRadius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: player.shownBase }
                    GradientStop { position: 1.0; color: player.shownDark }
                }
            }

            Column {
                id: leftColumn
                x: Theme.fsCardPadding
                y: Theme.fsCardPadding
                width: player.cardWidth - 2 * Theme.fsCardPadding
                    - (player.coverVisible ? player.innerHeight + 24 : 0)
                spacing: 20 + player.extraHeight / 2

                Column {
                    id: identity
                    width: parent.width
                    spacing: 4

                    MarqueeText {
                        objectName: "fullscreenTitle"
                        width: parent.width
                        text: player.track.title || ""
                        pixelSize: Theme.fsTitleSize
                        bold: true
                    }

                    Text {
                        objectName: "fullscreenArtist"
                        width: parent.width
                        text: player.track.artist && player.track.artist.length > 0
                            ? player.track.artist : "Unknown artist"
                        elide: Text.ElideRight
                        color: Qt.rgba(1, 1, 1, 0.88)
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsArtistSize
                    }

                    Text {
                        objectName: "fullscreenGenre"
                        visible: text.length > 0
                        width: parent.width
                        text: player.track.genre || ""
                        elide: Text.ElideRight
                        color: Qt.rgba(1, 1, 1, 0.62)
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fsGenreSize
                    }
                }

                Item {
                    width: parent.width
                    height: Theme.waveHeight

                    WaveformView {
                        objectName: "waveformView"
                        visible: player.playback.status !== "Error"
                        anchors.fill: parent
                        waveform: player.waveform
                        playback: player.playback
                    }

                    Row {
                        objectName: "fullscreenPlaybackError"
                        visible: player.playback.status === "Error"
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        spacing: 8

                        Text {
                            width: parent.width - 2 * 40 - 16
                            anchors.verticalCenter: parent.verticalCenter
                            text: player.playback.errorMessage || "Playback failed."
                            elide: Text.ElideRight
                            color: Theme.danger
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }

                        IconButton {
                            objectName: "fullscreenRetry"
                            width: 40
                            height: 40
                            icon: "play"
                            iconSize: 18
                            tip: "Retry"
                            onClicked: player.playback.retry()
                        }

                        IconButton {
                            objectName: "fullscreenNext"
                            width: 40
                            height: 40
                            icon: "next"
                            iconSize: 18
                            tip: "Next"
                            onClicked: player.playback.next()
                        }
                    }
                }

                Item {
                    width: parent.width
                    height: Theme.fsPlaySize

                    // The icon follows the player, never the hover.
                    Rectangle {
                        objectName: "fullscreenPlay"
                        width: Theme.fsPlaySize
                        height: width
                        radius: width / 2
                        color: "#FFFFFF"
                        scale: playMouse.pressed ? 0.94 : 1

                        Icon {
                            anchors.centerIn: parent
                            name: player.willPlay ? "pause" : "play"
                            size: Math.round(parent.width * 0.46)
                            color: player.shownDark
                        }

                        MouseArea {
                            id: playMouse
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: player.playback.togglePlay()
                        }
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.fsActionSpacing

                        IconButton {
                            objectName: "fullscreenLike"
                            width: 36
                            height: 36
                            hoverBackground: false
                            icon: player.liked ? "heart-filled" : "heart"
                            iconSize: Theme.fsActionIconSize
                            iconColor: player.liked ? Theme.secondary : Qt.rgba(1, 1, 1, 0.82)
                            hoverColor: player.liked ? Theme.secondary : "#FFFFFF"
                            tip: player.liked ? "Remove from Liked tracks" : "Add to Liked tracks"
                            onClicked: player.workspace.toggleLike(player.playback.playingId)
                        }

                        IconButton {
                            id: addButton
                            objectName: "fullscreenAddPlaylist"
                            width: 36
                            height: 36
                            hoverBackground: false
                            icon: player.inPlaylist ? "check" : "add-playlist"
                            iconSize: Theme.fsActionIconSize
                            iconColor: Qt.rgba(1, 1, 1, 0.82)
                            hoverColor: "#FFFFFF"
                            tip: "Add to playlist"
                            onClicked: player.openPlaylistMenu(addButton)
                        }

                        IconButton {
                            id: moreButton
                            objectName: "fullscreenMore"
                            width: 36
                            height: 36
                            hoverBackground: false
                            icon: "more"
                            iconSize: Theme.fsActionIconSize
                            iconColor: Qt.rgba(1, 1, 1, 0.82)
                            hoverColor: "#FFFFFF"
                            tip: "More"
                            onClicked: moreMenu.popup(moreButton, 0, -moreMenu.implicitHeight)
                        }
                    }
                }
            }

            // Square cover with rounded corners; not clickable.
            Item {
                id: coverFrame
                objectName: "fullscreenPlayerCover"
                visible: player.coverVisible
                x: player.cardWidth - Theme.fsCardPadding - player.innerHeight
                y: Theme.fsCardPadding
                width: player.innerHeight
                height: player.innerHeight

                CoverArt {
                    id: cover
                    anchors.fill: parent
                    visible: false
                    layer.enabled: true
                    pattern: player.track.cover !== undefined ? player.track.cover : -1
                    source: player.track.coverUrl || ""
                }

                Item {
                    id: coverMask
                    anchors.fill: parent
                    visible: false
                    layer.enabled: true

                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                    }
                }

                MultiEffect {
                    anchors.fill: parent
                    source: cover
                    maskEnabled: true
                    maskSource: coverMask
                }
            }
        }
    }

    // Page 2 slides up from below the view while the card moves up: with a single column,
    // its cards would show under the card on page 1.
    Item {
        id: page2
        objectName: "fullscreenPage2"
        visible: player.hasTrack && player.progress > 0
        y: player.height - player.progress * (player.height - Theme.fsPeek - Theme.fsTopMargin)
        width: parent.width
        height: player.page2Height
    }

    // The bottom of the card stays visible under a dark gradient on page 2, not clickable.
    Rectangle {
        objectName: "fullscreenVignette"
        z: 4
        visible: player.hasTrack
        width: parent.width
        height: Theme.fsVignetteHeight
        opacity: player.progress
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.editor }
            GradientStop { position: 0.55; color: Qt.rgba(Theme.editor.r, Theme.editor.g, Theme.editor.b, 0.6) }
            GradientStop { position: 1.0; color: Qt.rgba(Theme.editor.r, Theme.editor.g, Theme.editor.b, 0) }
        }
    }

    MouseArea {
        objectName: "fullscreenPeekAbsorber"
        z: 5
        width: parent.width
        height: Theme.fsTopMargin + Theme.fsPeek
        enabled: player.hasTrack && player.progress > 0.02
        hoverEnabled: true
    }

    IconButton {
        objectName: "exitFullscreen"
        z: 6
        anchors.top: parent.top
        anchors.topMargin: 16
        anchors.right: parent.right
        anchors.rightMargin: 16
        icon: "exit-fullscreen"
        iconSize: 18
        tip: "Exit fullscreen (Esc)"
        onClicked: player.workspace.setFullscreen(false)
    }

    component PageArrow: Rectangle {
        id: arrow

        property string icon: ""
        property string tip: ""
        signal clicked()

        z: 6
        width: 40
        height: 40
        radius: 20
        color: arrowMouse.containsMouse ? Theme.surface : Theme.editor
        border.width: 1
        border.color: Theme.separator

        Icon {
            anchors.centerIn: parent
            name: arrow.icon
            size: 18
            color: arrowMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
        }

        MouseArea {
            id: arrowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: arrow.clicked()
        }

        HoverTip {
            visible: arrow.tip.length > 0 && arrowMouse.containsMouse
            text: arrow.tip
        }
    }

    PageArrow {
        objectName: "fullscreenPageUp"
        visible: player.hasTrack && player.page === 1
        anchors.right: parent.right
        anchors.rightMargin: 16
        y: 16 + 32 + 10
        icon: "arrow-up"
        tip: "Back to the player"
        onClicked: player.workspace.setFullscreenPage(0)
    }

    PageArrow {
        objectName: "fullscreenPageDown"
        visible: player.hasTrack && player.page === 0
        anchors.right: parent.right
        anchors.rightMargin: 16
        y: player.height - Theme.islandMargin - Theme.islandHeight / 2 - height / 2
        icon: "arrow-down"
        tip: "Queue and track details"
        onClicked: player.workspace.setFullscreenPage(1)
    }

    function openPlaylistMenu(anchor) {
        playlistMenu.trackIds = [player.playback.playingId]
        playlistMenu.popup(anchor, 0, -playlistMenu.height)
    }

    PlayingTrackMenu {
        id: moreMenu
        workspace: player.workspace
        trackId: player.playback.playingId
        source: player.playback.playingSource
        onAddToPlaylistRequested: player.openPlaylistMenu(moreButton)
    }

    AddToPlaylistMenu {
        id: playlistMenu
        workspace: player.workspace
    }
}
