import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts
import Mtee

// Review prototype of the plan 100 fullscreen player. Everything is illustrative:
// simulated clock, no audio, no service, no file access. All numbers below are
// initial mock-up values; F2 opens a panel to change them and read them back.
ApplicationWindow {
    id: root
    visible: true
    width: 1440
    height: 900
    minimumWidth: 640
    minimumHeight: 480
    title: "MTEE — fullscreen player review"
    color: Theme.editor

    // ---- Review inputs ---------------------------------------------------------
    property string scene: "page1"
    property var extraTracks: []      // set by --covers
    property var audioRms: []         // set by --audio
    property string audioTitle: ""
    property string feedback: "Illustrative fullscreen · simulated clock, no audio, no files"

    // ---- Tuning (initial mock-up values, see the plan constants table) --------------
    QtObject {
        id: tune
        property int barWidth: 3
        property int barGap: 2
        property real waveHeight: 128
        property real gamma: 1.6
        property real shadowOpacity: 0.05
        property int pageDuration: 350
        property int peek: 32
        property int cardExtra: 60           // extra card height, shared between the two gaps
        property string playVariant: "A"     // A white, B black, C light accent
        property string p2Layout: "auto"     // auto, wide, narrow
        readonly property int cardRadius: 16
        readonly property int cardMaxWidth: 1400
        readonly property int cardPadding: 28
        readonly property int coverHideWidth: 820
        readonly property int titleSize: 34
        readonly property int artistSize: 18
        readonly property int genreSize: 13
        readonly property color fallbackCard: "#26262B"
        readonly property int accentFade: 1000
        readonly property int playSize: 56
        readonly property int actionIcon: 22
        readonly property int vignetteHeight: 96
        readonly property int topMargin: 16
        readonly property int queueRow: 56
        readonly property int queueCover: 44
        readonly property int topBlock: 64
        readonly property int wideThreshold: 1100
    }

    // ---- Mock library ------------------------------------------------------------
    function makeRms(seed, plan) {
        let s = seed
        function rnd() { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296 }
        const out = []
        for (let i = 0; i < 1200; ++i) {
            const t = i / 1200
            let base = 0.2
            for (const sec of plan) {
                if (t >= sec[0] && t < sec[1]) {
                    base = sec[2] + (sec[3] || 0) * (t - sec[0]) / (sec[1] - sec[0])
                    break
                }
            }
            const beat = 1 + 0.12 * Math.sin(i * 0.9) + 0.06 * Math.sin(i * 0.23)
            out.push(Math.max(0.01, base * beat * (0.88 + 0.24 * rnd())))
        }
        return out
    }
    // Intro, build-up, drop, break, a second drop 3 dB below the first, outro.
    readonly property var dropPlan: [[0, 0.1, 0.22, 0.1], [0.1, 0.25, 0.35, 0.25], [0.25, 0.5, 1.0],
                                     [0.5, 0.6, 0.2], [0.6, 0.9, 0.708], [0.9, 1.0, 0.3, -0.25]]
    readonly property var calmPlan: [[0, 0.3, 0.3, 0.2], [0.3, 0.7, 0.55], [0.7, 1.0, 0.45, -0.3]]
    function defaults(item) {
        return Object.assign({
            title: "Untitled", artist: "", genre: "", cover: null, file: "", coverColor: "",
            bpm: "", key: "", camelot: "", format: "FLAC", bitrate: "", year: "", album: "",
            sampleRate: "44.1 kHz", bitDepth: "16-bit", size: "", folder: "Night drive",
            duration: 312, plan: dropPlan, seed: 7
        }, item)
    }
    readonly property var builtIn: [
        defaults({title: "Control (Original Mix)", artist: "Northline", genre: "Techno",
                  cover: {bg: "#2F5BFF", fg: "#FFD23F", shape: 0}, coverColor: "#2F5BFF",
                  bpm: "128", key: "Am", camelot: "8A", format: "FLAC", bitrate: "1021 kbps",
                  year: "2024", album: "Night Pressings", size: "38.4 MB", duration: 342, seed: 11}),
        defaults({title: "Afterlight (Extended Mix)", artist: "Velar", genre: "Progressive House",
                  cover: {bg: "#E8D77A", fg: "#BFA83A", shape: 3}, coverColor: "#E8D77A",
                  bpm: "124", key: "F#m", camelot: "11A", format: "MP3", bitrate: "320 kbps",
                  year: "2023", album: "Afterlight EP", size: "13.1 MB", duration: 410, seed: 23}),
        defaults({title: "Grey Room", artist: "Second Signal", genre: "Ambient",
                  cover: {bg: "#5E5E64", fg: "#8E8E94", shape: 1}, coverColor: "",
                  bpm: "92", key: "Dm", camelot: "7A", format: "WAV", bitrate: "1411 kbps",
                  year: "2022", album: "Rooms", size: "52.0 MB", duration: 298, plan: calmPlan, seed: 31}),
        defaults({title: "Untitled sketch 07", artist: "", genre: "", cover: null, format: "AIFF",
                  duration: 187, seed: 47}),
        defaults({title: "Control (Original Mix) — Extended Festival Edit with a Very Long Subtitle That Has To Scroll",
                  artist: "Northline & Second Signal", genre: "Techno",
                  cover: {bg: "#17B26A", fg: "#0B3D2A", shape: 2}, coverColor: "#17B26A",
                  bpm: "130", key: "Cm", camelot: "5A", format: "FLAC", bitrate: "998 kbps",
                  year: "2025", album: "Festival Cuts", size: "44.7 MB", duration: 436, seed: 59})
    ]
    readonly property var tracks: {
        const list = builtIn.map(item => Object.assign({}, item))
        for (const item of list)
            item.rms = makeRms(item.seed, item.plan)
        if (audioRms.length > 0) {
            list[0].rms = audioRms
            if (audioTitle.length > 0)
                list[0].title = audioTitle
        }
        for (const extra of extraTracks) {
            const item = defaults(extra)
            item.rms = makeRms(item.title.length * 13 + 5, dropPlan)
            list.push(item)
        }
        return list
    }

    property int trackIndex: 0
    readonly property var track: tracks[Math.min(trackIndex, tracks.length - 1)]
    property bool hasTrack: true
    property bool playing: true
    property real position: 120
    property bool liked: false
    property bool inPlaylist: false
    property bool playbackError: false
    property string waveState: "ready"
    property real waveProgress: 0.42
    property real forcedHover: -1
    property int previewHoverRow: -1
    property int page: 0
    property real progress: 0          // 0 = page 1, 1 = page 2
    property bool fadeOn: true
    property bool wheelLocked: false
    property real wheelAccum: 0

    // ---- Accent colour (prototype of steps 5 and 6 of the plan algorithm) ----------
    function relativeLuminance(c) {
        function lin(v) { return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
        return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b)
    }
    function whiteContrast(c) { return 1.05 / (relativeLuminance(c) + 0.05) }
    function accentFrom(hex) {
        if (!hex || hex.length === 0)
            return null
        let c = Qt.color(hex)
        const hue = c.hsvHue
        const saturation = c.hsvSaturation
        let value = c.hsvValue
        let guard = 0
        while (whiteContrast(c) < 4.5 && value > 0.05 && guard++ < 40) {
            value -= 0.05
            c = Qt.hsva(hue, saturation, Math.max(0, value), 1)
        }
        return {base: c, dark: Qt.hsva(hue, saturation, c.hsvValue * 0.55, 1)}
    }
    readonly property var accent: accentFrom(track.coverColor)
    readonly property bool hasAccent: accent !== null
    readonly property color accentBase: hasAccent ? accent.base : tune.fallbackCard
    readonly property color accentDark: hasAccent ? accent.dark : tune.fallbackCard
    property color shownBase: accentBase
    property color shownDark: accentDark
    Behavior on shownBase { enabled: root.fadeOn; ColorAnimation { duration: tune.accentFade } }
    Behavior on shownDark { enabled: root.fadeOn; ColorAnimation { duration: tune.accentFade } }

    // ---- Geometry ------------------------------------------------------------------
    readonly property real viewW: width - Theme.activityBarWidth
    readonly property real viewH: height - Theme.titleBarHeight
    readonly property real reserve: Theme.islandHeight + 2 * Theme.islandMargin
    readonly property real sideMargin: Math.max(48, viewW * 0.06)
    readonly property real cardW: Math.min(tune.cardMaxWidth, viewW - 2 * sideMargin)
    readonly property bool coverVisible: cardW >= tune.coverHideWidth
    // The extra height is capped so the card never runs into the island.
    readonly property real baseInner: identity.implicitHeight + tune.waveHeight + tune.playSize + 40
    readonly property real extraHeight: Math.max(0, Math.min(tune.cardExtra,
        viewH - reserve - tune.topBlock - 8 - (baseInner + 2 * tune.cardPadding)))
    readonly property real innerH: leftColumn.implicitHeight
    readonly property real cardH: innerH + 2 * tune.cardPadding
    readonly property real cardTop: tune.topBlock + Math.max(0, (viewH - reserve - tune.topBlock - cardH) / 2)
    readonly property real cardBottom: cardTop + cardH
    readonly property real maxOffset: Math.max(0, cardBottom - tune.peek - tune.topMargin)
    readonly property real page2Height: Math.max(0, viewH - tune.peek - tune.topMargin - reserve)
    readonly property real islandWidth: Math.min(Theme.islandMaxWidth, viewW - 2 * 76)
    readonly property bool wide: tune.p2Layout === "wide" || (tune.p2Layout === "auto" && cardW >= tune.wideThreshold)
    readonly property string boardScene: scene === "waveform-variants" || scene === "play-variants" ? scene : ""

    function formatTime(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const h = Math.floor(total / 3600)
        const m = Math.floor((total % 3600) / 60)
        const s = total % 60
        const pad = s < 10 ? "0" + s : "" + s
        return h > 0 ? h + ":" + (m < 10 ? "0" : "") + m + ":" + pad : m + ":" + pad
    }

    // ---- Pages ---------------------------------------------------------------------
    function syncProgress(animated) {
        const target = page === 1 ? 1 : 0
        offsetAnimation.stop()
        if (animated) {
            offsetAnimation.to = target
            offsetAnimation.start()
        } else {
            progress = target
        }
    }
    function setPage(value) {
        if (!hasTrack)
            return
        page = value
    }
    onPageChanged: syncProgress(true)
    NumberAnimation {
        id: offsetAnimation
        target: root
        property: "progress"
        duration: tune.pageDuration
        easing.type: Easing.OutCubic
    }
    Timer {
        id: wheelUnlock
        interval: tune.pageDuration + 200
        onTriggered: root.wheelLocked = false
    }
    function handleWheel(wheel) {
        if (!hasTrack || wheelLocked)
            return
        const pixel = wheel.pixelDelta.y !== 0
        root.wheelAccum += pixel ? wheel.pixelDelta.y : wheel.angleDelta.y
        const threshold = pixel ? 60 : 120
        if (Math.abs(root.wheelAccum) >= threshold) {
            const target = root.wheelAccum < 0 ? 1 : 0
            root.wheelAccum = 0
            if (target !== page) {
                root.wheelLocked = true
                wheelUnlock.restart()
                setPage(target)
            }
        }
    }

    // ---- Simulated playback ------------------------------------------------------------
    Timer {
        interval: 100
        repeat: true
        running: root.playing && root.hasTrack && !root.playbackError && root.scene.indexOf("hover") < 0
        onTriggered: {
            root.position += 0.1
            if (root.position >= root.track.duration)
                root.position = 0
        }
    }
    function seekRatio(value) { position = value * track.duration }
    function nextTrack(step) {
        trackIndex = (trackIndex + step + tracks.length) % tracks.length
        position = 0
        liked = false
        inPlaylist = false
        playbackError = false
    }

    // ---- Scenes --------------------------------------------------------------------------
    function applyScene(name) {
        fadeOn = false
        rowMenu.close()
        addMenu.close()
        moreMenu.close()
        previewHoverRow = -1
        forcedHover = -1
        waveState = "ready"
        playbackError = false
        hasTrack = true
        liked = false
        inPlaylist = false
        trackIndex = 0
        playing = true
        let target = 0
        let at = 0.38
        switch (name) {
        case "page1-long-title": trackIndex = 4; break
        case "page1-pale-cover": trackIndex = 1; break
        case "page1-no-cover": trackIndex = 3; break
        case "page1-empty": hasTrack = false; break
        case "page1-generating": waveState = "generating"; break
        case "page1-error": playbackError = true; playing = false; break
        case "waveform-hover-ahead": playing = false; forcedHover = 0.62; at = 0.35; break
        case "waveform-hover-behind": playing = false; forcedHover = 0.15; at = 0.35; break
        case "page2": case "page2-narrow": target = 1; break
        case "queue-hover-menu": target = 1; previewHoverRow = 6; previewMenuTimer.restart(); break
        }
        position = tracks[trackIndex].duration * at
        page = target
        syncProgress(false)
        Qt.callLater(() => { fadeOn = true })
    }
    onSceneChanged: applyScene(scene)
    Component.onCompleted: applyScene(scene)

    Timer {
        id: previewMenuTimer
        interval: 220
        onTriggered: {
            const item = queueList.itemAtIndex(root.previewHoverRow)
            if (item) {
                rowMenu.current = false
                rowMenu.popup(item, item.width - 230, 40)
            }
        }
    }

    // ---- Mock window chrome (unchanged by the plan) -----------------------------------------
    Rectangle {
        id: titleBar
        z: 30
        width: parent.width
        height: Theme.titleBarHeight
        color: Theme.chrome
        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: "MTEE"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
        Text { anchors.centerIn: parent; text: root.feedback; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
        Row {
            anchors.right: parent.right
            height: parent.height
            Repeater {
                model: ["win-minimize", "win-maximize", "win-close"]
                delegate: Item {
                    required property string modelData
                    width: Theme.windowButtonWidth
                    height: parent.height
                    Icon { anchors.centerIn: parent; name: modelData; size: 14; color: Theme.textSecondary }
                }
            }
        }
    }
    Rectangle {
        id: activityBar
        z: 30
        y: Theme.titleBarHeight
        width: Theme.activityBarWidth
        height: parent.height - Theme.titleBarHeight
        color: Theme.chrome
        Column {
            Repeater {
                model: ["explorer", "playlists", "convert", "tasks", "plugins"]
                delegate: Item {
                    required property string modelData
                    width: Theme.activityBarWidth
                    height: Theme.activityBarWidth
                    Icon { anchors.centerIn: parent; name: modelData; size: 22; color: Theme.textSecondary }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.feedback = "Clicking an activity would leave fullscreen and open its sidebar" }
                }
            }
        }
        Column {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            Repeater {
                model: ["profile", "settings"]
                delegate: Item {
                    required property string modelData
                    width: Theme.activityBarWidth
                    height: Theme.activityBarWidth
                    Icon { anchors.centerIn: parent; name: modelData; size: 22; color: Theme.textMuted }
                }
            }
        }
    }

    // ---- Reusable mock pieces ------------------------------------------------------------
    component MockCover: Item {
        id: cover
        property var spec: null
        property string file: ""
        property real corner: 12

        Rectangle {
            anchors.fill: parent
            radius: cover.corner
            color: cover.spec ? cover.spec.bg : Theme.selection
            visible: cover.file.length === 0

            Rectangle {
                visible: cover.spec !== null && cover.spec.shape === 0
                width: cover.width * 0.56; height: width; radius: width / 2
                anchors.centerIn: parent
                color: cover.spec ? cover.spec.fg : "transparent"
            }
            Rectangle {
                visible: cover.spec !== null && cover.spec.shape === 1
                width: cover.width * 0.4; height: width; rotation: 45
                anchors.centerIn: parent
                color: cover.spec ? cover.spec.fg : "transparent"
            }
            Column {
                visible: cover.spec !== null && cover.spec.shape === 2
                anchors.bottom: parent.bottom
                anchors.bottomMargin: cover.height * 0.14
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: cover.height * 0.08
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        width: cover.width * (0.7 - index * 0.18)
                        height: cover.height * 0.1
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: cover.spec ? cover.spec.fg : "transparent"
                    }
                }
            }
            Rectangle {
                visible: cover.spec !== null && cover.spec.shape === 3
                width: cover.width * 0.5; height: width
                x: cover.width * 0.32; y: cover.height * 0.14
                color: "transparent"
                border.width: Math.max(2, cover.width * 0.06)
                border.color: cover.spec ? cover.spec.fg : "transparent"
            }
            Icon {
                visible: cover.spec === null
                anchors.centerIn: parent
                name: "music"
                size: Math.max(14, Math.round(cover.width * 0.42))
                color: Theme.textMuted
            }
        }
        Loader {
            anchors.fill: parent
            active: cover.file.length > 0
            sourceComponent: Item {
                Image { id: photo; anchors.fill: parent; source: cover.file; fillMode: Image.PreserveAspectCrop; visible: false; layer.enabled: true }
                Item {
                    id: mask
                    anchors.fill: parent
                    visible: false
                    layer.enabled: true
                    Rectangle { anchors.fill: parent; radius: cover.corner }
                }
                MultiEffect { anchors.fill: parent; source: photo; maskEnabled: true; maskSource: mask }
            }
        }
    }

    component PlayCircle: Rectangle {
        id: circle
        property string variant: "A"
        property color baseColor: root.shownBase
        property color darkColor: root.shownDark
        property bool playingState: root.playing
        signal clicked()
        width: tune.playSize
        height: width
        radius: width / 2
        color: variant === "A" ? "#FFFFFF" : variant === "B" ? "#0A0A0A" : Qt.lighter(baseColor, 1.7)
        scale: playMouse.pressed ? 0.94 : 1
        Icon {
            anchors.centerIn: parent
            name: circle.playingState ? "pause" : "play"
            size: Math.round(circle.width * 0.46)
            color: circle.variant === "A" ? circle.darkColor : circle.variant === "B" ? "#FFFFFF" : "#0A0A0A"
        }
        MouseArea { id: playMouse; anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: circle.clicked() }
    }

    component Panel: Rectangle {
        id: panel
        property string heading: ""
        default property alias content: body.data
        color: Theme.surface
        radius: tune.cardRadius
        Text {
            x: 20; y: 16
            text: panel.heading
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.bold: true
        }
        Item { id: body; x: 20; y: 56; width: panel.width - 40; height: panel.height - 56 - 16 }
    }

    component RoundIcon: Rectangle {
        id: round
        property string icon: ""
        property string tip: ""
        signal clicked()
        width: 40
        height: 40
        radius: 20
        color: roundMouse.containsMouse ? Theme.surface : Theme.editor
        border.width: 1
        border.color: Theme.separator
        Icon { anchors.centerIn: parent; name: round.icon; size: 18; color: roundMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary }
        MouseArea { id: roundMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: round.clicked() }
        HoverTip { visible: round.tip.length > 0 && roundMouse.containsMouse; text: round.tip }
    }

    // ---- The fullscreen view -------------------------------------------------------------------
    Item {
        id: view
        x: Theme.activityBarWidth
        y: Theme.titleBarHeight
        width: root.viewW
        height: root.viewH
        clip: true

        // Wheel on empty areas and on cards changes page; the Queue list consumes its own.
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            onWheel: wheel => root.handleWheel(wheel)
        }

        Text {
            visible: !root.hasTrack
            anchors.centerIn: parent
            text: "Play a track"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: 16
        }

        Item {
            id: pages
            visible: root.hasTrack
            y: -root.progress * root.maxOffset
            width: parent.width
            height: parent.height

            // Playing from (page 1 only: it scrolls away with the page)
            Column {
                x: 24
                y: 14
                spacing: 2
                SectionLabel { text: "Playing from folder" }
                Text {
                    text: "Night drive"
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
                        onClicked: root.feedback = "The source name would leave fullscreen and open this folder"
                    }
                }
            }

            // Main card
            Item {
                id: cardHolder
                x: (root.viewW - width) / 2
                y: root.cardTop
                width: root.cardW
                height: root.cardH

                Repeater {
                    model: 6
                    Rectangle {
                        required property int index
                        visible: !root.hasAccent
                        x: -(index + 1) * 4
                        y: -(index + 1) * 2 + 4
                        width: parent.width + (index + 1) * 8
                        height: parent.height + (index + 1) * 4
                        radius: tune.cardRadius + (index + 1) * 4
                        color: "#000000"
                        opacity: tune.shadowOpacity / 6
                    }
                }

                Rectangle {
                    id: card
                    objectName: "mainCard"
                    anchors.fill: parent
                    radius: tune.cardRadius
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: root.shownBase }
                        GradientStop { position: 1.0; color: root.shownDark }
                    }
                }

                Column {
                    id: leftColumn
                    x: tune.cardPadding
                    y: tune.cardPadding
                    width: root.cardW - 2 * tune.cardPadding - (root.coverVisible ? root.innerH + 24 : 0)
                    spacing: 20 + root.extraHeight / 2

                    Column {
                        id: identity
                        width: parent.width
                        spacing: 4

                        Fs100Marquee {
                            width: parent.width
                            text: root.track.title
                            pixelSize: tune.titleSize
                        }
                        Text {
                            width: parent.width
                            text: root.track.artist.length > 0 ? root.track.artist : "Unknown artist"
                            elide: Text.ElideRight
                            color: Qt.rgba(1, 1, 1, 0.88)
                            font.family: Theme.fontFamily
                            font.pixelSize: tune.artistSize
                        }
                        Text {
                            visible: root.track.genre.length > 0
                            width: parent.width
                            text: root.track.genre
                            elide: Text.ElideRight
                            color: Qt.rgba(1, 1, 1, 0.62)
                            font.family: Theme.fontFamily
                            font.pixelSize: tune.genreSize
                        }
                    }

                    Item {
                        width: parent.width
                        height: tune.waveHeight

                        Fs100Waveform {
                            id: waveform
                            visible: !root.playbackError
                            anchors.fill: parent
                            rms: root.track.rms
                            barWidth: tune.barWidth
                            barGap: tune.barGap
                            waveHeight: tune.waveHeight
                            gamma: tune.gamma
                            ratio: root.position / Math.max(1, root.track.duration)
                            duration: root.track.duration
                            waveState: root.waveState
                            progress: root.waveProgress
                            forcedHover: root.forcedHover
                            onSeekRequested: value => root.seekRatio(value)
                            onPlayRequested: root.playing = true
                            onNextRequested: { root.nextTrack(1); root.feedback = "Release beyond the end: next track" }
                            onRetryRequested: root.waveState = "generating"
                            onScrubStatusChanged: root.feedback = scrubStatus
                        }

                        Row {
                            visible: root.playbackError
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width
                            spacing: 8
                            Text {
                                width: parent.width - 2 * 40 - 16
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Playback failed: the file could not be opened."
                                elide: Text.ElideRight
                                color: Theme.danger
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeBody
                            }
                            IconButton { icon: "play"; iconSize: 18; width: 40; height: 40; tip: "Retry"; onClicked: root.playbackError = false }
                            IconButton { icon: "next"; iconSize: 18; width: 40; height: 40; tip: "Next"; onClicked: root.nextTrack(1) }
                        }
                    }

                    Item {
                        width: parent.width
                        height: tune.playSize

                        PlayCircle {
                            variant: tune.playVariant
                            onClicked: root.playing = !root.playing
                        }

                        Row {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 8
                            IconButton {
                                width: 36; height: 36
                                hoverBackground: false
                                icon: root.liked ? "heart-filled" : "heart"
                                iconSize: tune.actionIcon
                                iconColor: root.liked ? Theme.secondary : Qt.rgba(1, 1, 1, 0.82)
                                hoverColor: root.liked ? Theme.secondary : "#FFFFFF"
                                tip: root.liked ? "Remove from Liked tracks" : "Add to Liked tracks"
                                onClicked: root.liked = !root.liked
                            }
                            IconButton {
                                id: plusButton
                                width: 36; height: 36
                                hoverBackground: false
                                icon: root.inPlaylist ? "check" : "add-playlist"
                                iconSize: tune.actionIcon
                                iconColor: Qt.rgba(1, 1, 1, 0.82)
                                hoverColor: "#FFFFFF"
                                tip: "Add to playlist"
                                onClicked: addMenu.popup(plusButton, 0, -addMenu.implicitHeight)
                            }
                            IconButton {
                                id: moreButton
                                width: 36; height: 36
                                hoverBackground: false
                                icon: "more"
                                iconSize: tune.actionIcon
                                iconColor: Qt.rgba(1, 1, 1, 0.82)
                                hoverColor: "#FFFFFF"
                                tip: "More"
                                onClicked: moreMenu.popup(moreButton, 0, -moreMenu.implicitHeight)
                            }
                        }
                    }
                }

                MockCover {
                    visible: root.coverVisible
                    x: root.cardW - tune.cardPadding - root.innerH
                    y: tune.cardPadding
                    width: root.innerH
                    height: root.innerH
                    spec: root.track.cover
                    file: root.track.file
                    corner: 12
                }
            }

        }

        // Page 2 slides up from below the view while the main card moves up by ``maxOffset``:
        // with one column, the cards would show under the main card on page 1.
        Item {
            id: page2
            visible: root.hasTrack && root.progress > 0
            y: root.viewH - root.progress * (root.viewH - tune.peek - tune.topMargin)
            width: root.viewW
            height: root.page2Height

            Item {
                id: cards
                x: (root.viewW - root.cardW) / 2
                y: tune.topMargin
                width: root.cardW
                height: root.page2Height - tune.topMargin
                readonly property real gap: 20
                readonly property real leftW: (width - gap) * 0.58
                readonly property real narrowRow: 180

                Panel {
                    id: artistCard
                    heading: "Artist"
                    x: 0
                    y: 0
                    width: root.wide ? cards.leftW : (cards.width - cards.gap) / 2
                    height: root.wide ? (cards.height - cards.gap) * 0.4 : cards.narrowRow
                    Column {
                        spacing: 8
                        width: parent.width
                        Text {
                            width: parent.width
                            text: root.track.artist.length > 0 ? root.track.artist : "Unknown artist"
                            elide: Text.ElideRight
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: 18
                        }
                        Text {
                            text: "Artist details will come later."
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSecondary
                        }
                    }
                }

                Panel {
                    id: detailsCard
                    objectName: "trackDetailsCard"
                    heading: "Track details"
                    x: root.wide ? 0 : artistCard.width + cards.gap
                    y: root.wide ? artistCard.height + cards.gap : 0
                    width: root.wide ? cards.leftW : (cards.width - cards.gap) / 2
                    height: root.wide ? cards.height - artistCard.height - cards.gap : cards.narrowRow

                    // One label/value column when the card is tall enough, otherwise two pairs per row.
                    readonly property bool single: root.wide && height >= 385

                    GridLayout {
                        width: parent.width
                        columns: detailsCard.single ? 1 : 2
                        columnSpacing: 16
                        rowSpacing: detailsCard.single ? 4 : 2
                        Repeater {
                            model: [
                                {label: "BPM", value: root.track.bpm},
                                {label: "Key", value: root.track.key, camelot: root.track.camelot},
                                {label: "Genre", value: root.track.genre},
                                {label: "Date", value: root.track.year},
                                {label: "Format", value: root.track.format},
                                {label: "Bitrate", value: root.track.bitrate},
                                {label: "Folder", value: root.track.folder},
                                {label: "Album", value: root.track.album, candidate: true},
                                {label: "Duration", value: root.formatTime(root.track.duration), candidate: true},
                                {label: "Sample rate", value: root.track.sampleRate, candidate: true},
                                {label: "Bit depth", value: root.track.bitDepth, candidate: true},
                                {label: "Size", value: root.track.size, candidate: true}
                            ]
                            delegate: Item {
                                id: cell
                                required property var modelData
                                readonly property real labelWidth: detailsCard.single ? 84 : 76
                                readonly property bool hasBadge: modelData.camelot !== undefined && modelData.camelot.length > 0
                                Layout.fillWidth: true
                                implicitHeight: detailsCard.single ? 20 : 18
                                Text {
                                    width: cell.labelWidth
                                    text: cell.modelData.label + (cell.modelData.candidate === true ? " *" : "")
                                    elide: Text.ElideRight
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: detailsCard.single ? Theme.fontSizeSecondary : Theme.fontSizeSmall
                                }
                                Row {
                                    x: cell.labelWidth + 6
                                    width: cell.width - x
                                    spacing: 6
                                    Text {
                                        width: Math.min(implicitWidth, parent.width - (cell.hasBadge ? 32 : 0))
                                        text: cell.modelData.value && cell.modelData.value.length > 0 ? cell.modelData.value : "—"
                                        elide: Text.ElideRight
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: detailsCard.single ? Theme.fontSizeSecondary : Theme.fontSizeSmall
                                    }
                                    Rectangle {
                                        visible: cell.hasBadge
                                        width: camelotText.implicitWidth + 10
                                        height: 16
                                        radius: Theme.badgeRadius
                                        color: Theme.camelotColor(cell.modelData.camelot || "")
                                        Text { id: camelotText; anchors.centerIn: parent; text: cell.modelData.camelot || ""; color: Theme.textOnColor; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
                                    }
                                }
                            }
                        }
                    }

                    Text {
                        visible: detailsCard.single
                        anchors.bottom: parent.bottom
                        anchors.right: parent.right
                        text: "* candidate field: keep or drop at review"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 10
                    }
                }

                Panel {
                    id: queueCard
                    objectName: "queueCard"
                    heading: "Queue"
                    x: root.wide ? cards.leftW + cards.gap : 0
                    y: root.wide ? 0 : cards.narrowRow + cards.gap
                    width: root.wide ? cards.width - cards.leftW - cards.gap : cards.width
                    height: root.wide ? cards.height : cards.height - cards.narrowRow - cards.gap

                    ListView {
                        id: queueList
                        anchors.fill: parent
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        model: root.queueItems
                        ScrollBar.vertical: ThinScrollBar {}
                        delegate: Item {
                            id: row
                            required property var modelData
                            required property int index
                            readonly property bool isSection: modelData.kind === "section"
                            readonly property bool current: modelData.current === true
                            readonly property bool unavailable: modelData.available === false
                            readonly property bool hovered: rowMouse.containsMouse || coverMouse.containsMouse
                                || moreMouse.containsMouse || root.previewHoverRow === index
                            width: queueList.width
                            height: isSection ? 34 : tune.queueRow

                            Text {
                                visible: row.isSection
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                anchors.verticalCenterOffset: 4
                                text: row.modelData.label || ""
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                                font.bold: true
                            }

                            Rectangle {
                                visible: !row.isSection
                                anchors.fill: parent
                                anchors.rightMargin: 8
                                color: row.hovered ? Theme.selection : "transparent"
                                opacity: row.unavailable ? 0.6 : 1
                            }
                            MouseArea {
                                id: rowMouse
                                visible: !row.isSection
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.RightButton
                                onClicked: { rowMenu.current = row.current; rowMenu.popup() }
                            }
                            MockCover {
                                id: rowCover
                                visible: !row.isSection
                                x: 6
                                anchors.verticalCenter: parent.verticalCenter
                                width: tune.queueCover
                                height: tune.queueCover
                                corner: 4
                                opacity: row.unavailable ? 0.5 : 1
                                spec: row.current ? root.track.cover : (row.modelData.cover || null)
                                file: row.current ? root.track.file : ""
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 4
                                    color: "#000000"
                                    opacity: row.current || row.hovered ? 0.45 : 0
                                    Behavior on opacity { NumberAnimation { duration: 120 } }
                                }
                                Icon {
                                    anchors.centerIn: parent
                                    name: row.current ? (root.playing ? "pause" : "play") : "play"
                                    size: 18
                                    color: "#FFFFFF"
                                    opacity: row.current || row.hovered ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: 120 } }
                                }
                                MouseArea {
                                    id: coverMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (row.current)
                                            root.playing = !root.playing
                                        else
                                            root.feedback = "Clicking the cover would play this occurrence"
                                    }
                                }
                            }
                            Column {
                                visible: !row.isSection
                                anchors.left: rowCover.right
                                anchors.leftMargin: 12
                                anchors.right: moreButtonQueue.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2
                                Text {
                                    width: parent.width
                                    text: row.current ? root.track.title : (row.modelData.title || "")
                                    elide: Text.ElideRight
                                    color: row.current ? Theme.primary : row.unavailable ? Theme.textMuted : Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeBody
                                }
                                Text {
                                    width: parent.width
                                    text: row.unavailable ? "Unavailable" : (row.current ? (root.track.artist || "Unknown artist") : (row.modelData.artist || ""))
                                    elide: Text.ElideRight
                                    color: row.unavailable ? Theme.danger : Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }
                            }
                            Item {
                                id: moreButtonQueue
                                visible: !row.isSection
                                anchors.right: parent.right
                                anchors.rightMargin: 14
                                anchors.verticalCenter: parent.verticalCenter
                                width: 28
                                height: 28
                                Icon {
                                    anchors.centerIn: parent
                                    name: "more"
                                    size: 18
                                    color: moreMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                                    opacity: row.hovered ? 1 : 0
                                }
                                MouseArea {
                                    id: moreMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: { rowMenu.current = row.current; rowMenu.popup(moreButtonQueue, 0, 28) }
                                }
                            }
                        }
                    }

                    // The list consumes the wheel, including at its bounds (P5).
                    MouseArea {
                        anchors.fill: queueList
                        acceptedButtons: Qt.NoButton
                        onWheel: wheel => {
                            const max = Math.max(0, queueList.contentHeight - queueList.height)
                            queueList.contentY = Math.max(0, Math.min(max, queueList.contentY - wheel.angleDelta.y * 0.5))
                            wheel.accepted = true
                        }
                    }
                }
            }
        }

        // ---- Fixed overlays ----------------------------------------------------------------
        Rectangle {
            id: vignette
            visible: root.hasTrack
            z: 4
            width: parent.width
            height: tune.vignetteHeight
            opacity: root.progress
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.editor }
                GradientStop { position: 0.55; color: Qt.rgba(0x18 / 255, 0x18 / 255, 0x1B / 255, 0.6) }
                GradientStop { position: 1.0; color: Qt.rgba(0x18 / 255, 0x18 / 255, 0x1B / 255, 0) }
            }
        }
        MouseArea {
            z: 5
            width: parent.width
            height: tune.topMargin + tune.peek
            enabled: root.hasTrack && root.progress > 0.02
            hoverEnabled: true
        }

        IconButton {
            objectName: "exitFullscreen"
            z: 6
            x: root.viewW - 16 - width
            y: 16
            icon: "exit-fullscreen"
            iconSize: 18
            tip: "Exit fullscreen (Esc)"
            onClicked: root.feedback = "Would leave fullscreen"
        }
        RoundIcon {
            visible: root.hasTrack && root.page === 1
            z: 6
            x: root.viewW - 16 - width - 0
            y: 16 + 32 + 10
            icon: "arrow-up"
            tip: "Back to the player"
            onClicked: root.setPage(0)
        }
        RoundIcon {
            visible: root.hasTrack && root.page === 0
            z: 6
            x: root.viewW - 16 - width
            y: root.viewH - Theme.islandMargin - Theme.islandHeight / 2 - height / 2
            icon: "arrow-down"
            tip: "Queue and track details"
            onClicked: root.setPage(1)
        }

        // Island: same content as in normal mode, fixed on both pages.
        Rectangle {
            id: island
            objectName: "playerIsland"
            visible: root.hasTrack
            z: 8
            width: root.islandWidth
            height: Theme.islandHeight
            x: (root.viewW - width) / 2
            y: root.viewH - Theme.islandMargin - height
            color: Theme.surface
            border.width: 1
            border.color: Theme.separator
            MouseArea { anchors.fill: parent }

            MockCover {
                id: islandCover
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                width: 48
                height: 48
                corner: 0
                spec: root.track.cover
                file: root.track.file
            }
            Column {
                id: islandIdentity
                anchors.left: islandCover.right
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(40, island.width * 0.3 - 48 - 12 - 12 - 26 - 8)
                spacing: 2
                Text {
                    width: parent.width
                    text: root.track.title
                    elide: Text.ElideRight
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }
                Text {
                    width: parent.width
                    text: root.track.artist.length > 0 ? root.track.artist : "Unknown artist"
                    elide: Text.ElideRight
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
            IconButton {
                id: islandAdd
                anchors.left: islandIdentity.right
                anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                width: 26
                hoverBackground: false
                icon: root.inPlaylist ? "check" : "add-playlist"
                iconSize: 18
                iconColor: root.inPlaylist ? Theme.secondary : Theme.textSecondary
                hoverColor: Theme.secondary
                tip: "Add to playlist"
                onClicked: addMenu.popup(islandAdd, 0, -addMenu.implicitHeight)
            }

            Column {
                anchors.centerIn: parent
                width: parent.width * 0.4
                spacing: 2
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8
                    IconButton { anchors.verticalCenter: parent.verticalCenter; hoverBackground: false; icon: "shuffle"; iconSize: 18 }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; hoverBackground: false; icon: "previous"; iconSize: 18; onClicked: root.nextTrack(-1) }
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 32
                        height: 32
                        color: Theme.primary
                        Icon { anchors.centerIn: parent; name: root.playing ? "pause" : "play"; size: 16; color: Theme.textOnColor }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.playing = !root.playing }
                    }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; hoverBackground: false; icon: "next"; iconSize: 18; onClicked: root.nextTrack(1) }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; hoverBackground: false; icon: "repeat"; iconSize: 18 }
                }
                Row {
                    width: parent.width
                    spacing: 8
                    Text {
                        width: 36
                        horizontalAlignment: Text.AlignRight
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.formatTime(root.position)
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                        font.features: { "tnum": 1 }
                    }
                    LineSlider {
                        width: parent.width - 88
                        anchors.verticalCenter: parent.verticalCenter
                        from: 0
                        to: root.track.duration
                        value: root.position
                        onMoved: value => root.position = value
                    }
                    Text {
                        width: 36
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.formatTime(root.track.duration)
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                        font.features: { "tnum": 1 }
                    }
                }
            }

            Row {
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                IconButton {
                    objectName: "islandQueueButton"
                    anchors.verticalCenter: parent.verticalCenter
                    hoverBackground: false
                    icon: "queue"
                    iconSize: 18
                    active: root.page === 1
                    tip: "Queue and track details"
                    onClicked: root.setPage(root.page === 1 ? 0 : 1)
                }
                IconButton { anchors.verticalCenter: parent.verticalCenter; hoverBackground: false; icon: "volume"; iconSize: 18 }
                LineSlider {
                    visible: island.width >= 760
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(96, Math.max(48, island.width * 0.08))
                    from: 0
                    to: 100
                    value: 70
                }
                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    hoverBackground: false
                    icon: "exit-fullscreen"
                    iconSize: 18
                    tip: "Exit fullscreen (Esc)"
                    onClicked: root.feedback = "Would leave fullscreen"
                }
            }
        }
    }

    // ---- Queue content ---------------------------------------------------------------------------
    function rowCover(index) {
        const colours = ["#6A3FD1", "#D14B3F", "#2B9C8E", "#C79A2B", "#3F7AD1", "#B23F8A"]
        return {bg: colours[index % colours.length], fg: "#FFFFFF33", shape: index % 4}
    }
    readonly property var queueItems: {
        const list = [
            {kind: "section", label: "Now playing"},
            {kind: "row", current: true},
            {kind: "section", label: "Next in queue"}
        ]
        const manual = [["Low Orbit", "Velar"], ["Wired", "Second Signal"]]
        manual.forEach((item, i) => list.push({kind: "row", title: item[0], artist: item[1], cover: rowCover(i), available: true}))
        list.push({kind: "section", label: "Next from: Night drive"})
        const context = [["Afterlight", "Northline"], ["Last Exit", "Second Signal"], ["Lost Signal", "Unknown artist", false],
                         ["Glass Hours", "Velar"], ["Neon Tide", "Northline"], ["Slow Static", "Second Signal"],
                         ["Night Bus", "Velar"], ["Ferrofluid", "Northline"], ["Hollow Pines", "Second Signal"],
                         ["Salt Circuit", "Velar"]]
        context.forEach((item, i) => list.push({kind: "row", title: item[0], artist: item[1],
                                                 cover: rowCover(i + 2), available: item[2] !== false}))
        return list
    }

    // ---- Menus -----------------------------------------------------------------------------------
    AppMenu {
        id: addMenu
        AppMenuItem { text: "New playlist…" }
        AppMenuSeparator {}
        AppMenuItem { text: "Night drive"; mark: root.inPlaylist; onTriggered: root.inPlaylist = !root.inPlaylist }
        AppMenuItem { text: "Warm-up" }
        AppMenuItem { text: "Peak hour" }
    }
    AppMenu {
        id: moreMenu
        AppMenuItem { text: "Edit info" }
        AppMenuItem { text: "Add to playlist…" }
        AppMenuItem { text: "Convert…" }
        AppMenuItem { text: "Analyze" }
        AppMenuItem { text: "Re-analyze" }
        AppMenuItem { text: "Show in Explorer" }
    }
    AppMenu {
        id: rowMenu
        property bool current: false
        AppMenuItem { text: "Remove from queue"; visible: !rowMenu.current; height: visible ? implicitHeight : 0 }
        AppMenuItem { text: "Go to folder" }
        AppMenuItem { text: "Edit info" }
    }

    // ---- Keys ------------------------------------------------------------------------------------------
    Shortcut { sequences: ["PgDown", "Down"]; onActivated: root.setPage(1) }
    Shortcut { sequences: ["PgUp", "Up"]; onActivated: root.setPage(0) }
    Shortcut { sequence: "F2"; onActivated: tuning.visible = !tuning.visible }
    Shortcut { sequence: "Escape"; onActivated: { rowMenu.close(); addMenu.close(); moreMenu.close() } }

    // ---- Comparison boards (captures) ----------------------------------------------------------------
    Rectangle {
        id: board
        z: 40
        visible: root.boardScene.length > 0
        anchors.fill: parent
        anchors.topMargin: Theme.titleBarHeight
        color: Theme.editor

        Text {
            x: 28; y: 16
            text: root.boardScene === "waveform-variants"
                ? "Waveform variants · rows: bars A 2/1 px, B 3/2 px, C 4/2 px · columns: gamma 1.0, 1.6, 2.2 · same fictive signal (intro, break, two drops 3 dB apart)"
                : "Play button variants · columns: A white circle, B black circle, C light accent circle · rows: vivid, pale (darkened), grey (fallback) covers"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Grid {
            x: 28
            y: 52
            columns: 3
            columnSpacing: 20
            rowSpacing: 20
            visible: root.boardScene === "waveform-variants"
            Repeater {
                model: 9
                delegate: Rectangle {
                    required property int index
                    readonly property var bars: [[2, 1, "A"], [3, 2, "B"], [4, 2, "C"]][Math.floor(index / 3)]
                    readonly property real gammaValue: [1.0, 1.6, 2.2][index % 3]
                    width: (root.width - 56 - 40) / 3
                    height: (root.height - Theme.titleBarHeight - 52 - 20 - 40) / 3
                    radius: tune.cardRadius
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: root.builtIn[0].coverColor }
                        GradientStop { position: 1.0; color: root.accentFrom(root.builtIn[0].coverColor).dark }
                    }
                    Text {
                        x: 16; y: 10
                        text: "Bars " + parent.bars[2] + " (" + parent.bars[0] + "/" + parent.bars[1] + ") · gamma " + parent.gammaValue.toFixed(1)
                        color: Qt.rgba(1, 1, 1, 0.85)
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                        font.bold: true
                    }
                    Fs100Waveform {
                        x: 16
                        y: 36
                        width: parent.width - 32
                        height: Math.min(tune.waveHeight, parent.height - 50)
                        waveHeight: height
                        rms: root.tracks[0].rms
                        barWidth: parent.bars[0]
                        barGap: parent.bars[1]
                        gamma: parent.gammaValue
                        ratio: 0.38
                        duration: root.tracks[0].duration
                        timeColumn: 40
                    }
                }
            }
        }

        Grid {
            x: 28
            y: 52
            columns: 3
            columnSpacing: 20
            rowSpacing: 20
            visible: root.boardScene === "play-variants"
            Repeater {
                model: 9
                delegate: Rectangle {
                    id: variantCard
                    required property int index
                    readonly property string variantName: ["A", "B", "C"][index % 3]
                    readonly property var cover: root.builtIn[[0, 1, 2][Math.floor(index / 3)]]
                    readonly property var tone: root.accentFrom(cover.coverColor)
                    readonly property color baseColor: tone ? tone.base : tune.fallbackCard
                    readonly property color darkColor: tone ? tone.dark : tune.fallbackCard
                    width: (root.width - 56 - 40) / 3
                    height: (root.height - Theme.titleBarHeight - 52 - 20 - 40) / 3
                    radius: tune.cardRadius
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: variantCard.baseColor }
                        GradientStop { position: 1.0; color: variantCard.darkColor }
                    }
                    Text { x: 24; y: 18; text: variantCard.cover.title; color: "#FFFFFF"; font.family: Theme.fontFamily; font.pixelSize: 22; font.bold: true }
                    Text { x: 24; y: 50; text: variantCard.cover.artist + " · variant " + variantCard.variantName + (variantCard.tone ? "" : " · grey fallback"); color: Qt.rgba(1, 1, 1, 0.75); font.family: Theme.fontFamily; font.pixelSize: 14 }
                    PlayCircle {
                        x: 24
                        y: parent.height - height - 24
                        variant: variantCard.variantName
                        baseColor: variantCard.baseColor
                        darkColor: variantCard.darkColor
                        playingState: false
                    }
                    Row {
                        anchors.right: parent.right
                        anchors.rightMargin: 24
                        y: parent.height - 36 - 24 + 10
                        spacing: 10
                        Icon { name: "heart"; size: 22; color: Qt.rgba(1, 1, 1, 0.82) }
                        Icon { name: "add-playlist"; size: 22; color: Qt.rgba(1, 1, 1, 0.82) }
                        Icon { name: "more"; size: 22; color: Qt.rgba(1, 1, 1, 0.82) }
                    }
                }
            }
        }
    }

    // ---- Tuning panel (F2) --------------------------------------------------------------------------
    Rectangle {
        id: tuning
        z: 60
        visible: false
        x: parent.width - width - 12
        y: Theme.titleBarHeight + 12
        width: 330
        height: Math.min(parent.height - Theme.titleBarHeight - 24, controlsColumn.implicitHeight + 24)
        color: Theme.sidebar
        border.width: 1
        border.color: Theme.separator
        clip: true

        Flickable {
            anchors.fill: parent
            anchors.margins: 12
            contentHeight: controlsColumn.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: controlsColumn
                width: parent.width
                spacing: 8

                Text { text: "Tuning · F2 to hide"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14; font.bold: true }

                component Slide: Item {
                    id: slide
                    property string label: ""
                    property real from: 0
                    property real to: 1
                    property real value: 0
                    property int decimals: 0
                    signal moved(real value)
                    width: controlsColumn.width
                    height: 24
                    Text { width: 118; anchors.verticalCenter: parent.verticalCenter; text: slide.label; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    LineSlider {
                        x: 122
                        width: parent.width - 122 - 50
                        anchors.verticalCenter: parent.verticalCenter
                        from: slide.from
                        to: slide.to
                        value: slide.value
                        onMoved: v => slide.moved(slide.decimals > 0 ? Number(v.toFixed(slide.decimals)) : Math.round(v))
                    }
                    Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: slide.value.toFixed(slide.decimals); color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                }
                component Choice: Row {
                    id: choice
                    property string label: ""
                    property var options: []
                    property string current: ""
                    signal picked(string option)
                    spacing: 4
                    Text { width: 118; anchors.verticalCenter: parent.verticalCenter; text: choice.label; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    Repeater {
                        model: choice.options
                        delegate: TextButton {
                            required property string modelData
                            implicitHeight: 26
                            text: modelData
                            kind: modelData === choice.current ? "primary" : "neutral"
                            onClicked: choice.picked(modelData)
                        }
                    }
                }

                Choice { label: "Bar variant"; options: ["A 2/1", "B 3/2", "C 4/2"]
                    current: tune.barWidth === 2 && tune.barGap === 1 ? "A 2/1" : tune.barWidth === 3 && tune.barGap === 2 ? "B 3/2" : tune.barWidth === 4 && tune.barGap === 2 ? "C 4/2" : ""
                    onPicked: option => { const v = {"A 2/1": [2, 1], "B 3/2": [3, 2], "C 4/2": [4, 2]}[option]; tune.barWidth = v[0]; tune.barGap = v[1] } }
                Slide { label: "Bar width (px)"; from: 1; to: 8; value: tune.barWidth; onMoved: v => tune.barWidth = v }
                Slide { label: "Bar gap (px)"; from: 1; to: 8; value: tune.barGap; onMoved: v => tune.barGap = v }
                Slide { label: "Card extra height"; from: 0; to: 200; value: tune.cardExtra; onMoved: v => tune.cardExtra = v }
                Slide { label: "Wave height (px)"; from: 60; to: 200; value: tune.waveHeight; onMoved: v => tune.waveHeight = v }
                Slide { label: "Gamma"; from: 1; to: 2.5; decimals: 1; value: tune.gamma; onMoved: v => tune.gamma = v }
                Slide { label: "Fallback shadow"; from: 0; to: 0.5; decimals: 2; value: tune.shadowOpacity; onMoved: v => tune.shadowOpacity = v }
                Slide { label: "Page duration (ms)"; from: 150; to: 700; value: tune.pageDuration; onMoved: v => tune.pageDuration = v }
                Slide { label: "Peek (px)"; from: 16; to: 80; value: tune.peek; onMoved: v => tune.peek = v }
                Choice { label: "Play variant"; options: ["A", "B", "C"]; current: tune.playVariant; onPicked: option => tune.playVariant = option }
                Choice { label: "Page 2 layout"; options: ["auto", "wide", "narrow"]; current: tune.p2Layout; onPicked: option => tune.p2Layout = option }
                Choice { label: "Waveform state"; options: ["ready", "generating", "unavailable"]; current: root.waveState; onPicked: option => root.waveState = option }
                Choice { label: "Playback error"; options: ["off", "on"]; current: root.playbackError ? "on" : "off"; onPicked: option => root.playbackError = option === "on" }
                Choice { label: "Track"; options: root.tracks.map((item, i) => "" + (i + 1)); current: "" + (root.trackIndex + 1); onPicked: option => root.nextTrack(Number(option) - 1 - root.trackIndex) }

                Text { text: "Current values (copy into the Decision Log)"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
                TextEdit {
                    width: parent.width
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                    text: "waveBarWidth/waveBarGap " + tune.barWidth + "/" + tune.barGap
                        + " · cardExtra " + tune.cardExtra
                        + " · waveHeight " + tune.waveHeight
                        + " · waveGamma " + tune.gamma.toFixed(1)
                        + " · fsShadowOpacity " + tune.shadowOpacity.toFixed(2)
                        + " · fsPageDuration " + tune.pageDuration
                        + " · fsPeek " + tune.peek
                        + " · play " + tune.playVariant
                        + " · page 2 " + tune.p2Layout
                }
            }
        }
    }
}
