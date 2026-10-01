import QtQuick
import Mtee

// Review prototype of the plan 100 waveform: symmetric rounded bars, hover
// colouring, scrub on the simulated clock (no sound), two stacked times on the right.
// Heights come from RMS energy normalised per track, then raised to ``gamma``.
Item {
    id: wave

    property var rms: []
    property int barWidth: 3
    property int barGap: 2
    property real waveHeight: 128
    property real minBar: 2
    property real gamma: 1.6
    property real ratio: 0
    property real duration: 0
    property bool seekable: true
    property string waveState: "ready"   // ready, generating, unavailable
    property real progress: 0
    property string message: "Waveform unavailable"
    property color playedColor: "#FFFFFF"
    property color unplayedColor: "#7C7C82"
    property color aheadColor: "#B9B9BF"
    property int playheadWidth: 2
    property int timeColumn: 48
    property real forcedHover: -1        // review captures only: hover as a 0..1 ratio
    readonly property bool ready: waveState === "ready"
    readonly property int barCount: Math.max(1, Math.floor((plotArea.width + barGap) / (barWidth + barGap)))
    readonly property real span: levels.length * barWidth + Math.max(0, levels.length - 1) * barGap
    readonly property real hoverPx: forcedHover >= 0 ? forcedHover * span
        : area.pressed ? Math.max(0, Math.min(span, area.mouseX))
        : area.containsMouse ? Math.max(0, Math.min(span, area.mouseX)) : -1
    readonly property real hoverRatio: hoverPx >= 0 && span > 0 ? hoverPx / span : -1
    property string scrubStatus: ""
    signal seekRequested(real ratio)
    signal playRequested()
    signal nextRequested()
    signal retryRequested()

    implicitHeight: waveHeight

    readonly property var levels: {
        const n = rms.length
        if (n === 0)
            return []
        const bars = Math.min(barCount, n)
        const energies = []
        let peak = 0
        for (let i = 0; i < bars; ++i) {
            const from = Math.floor(i * n / bars)
            const to = Math.max(from + 1, Math.floor((i + 1) * n / bars))
            let sum = 0
            for (let k = from; k < to; ++k)
                sum += rms[k] * rms[k]
            const energy = Math.sqrt(sum / (to - from))
            energies.push(energy)
            peak = Math.max(peak, energy)
        }
        return energies.map(energy => peak > 0 ? Math.min(1, Math.pow(energy / peak, gamma)) : 0)
    }

    function barColor(x, p, h) {
        if (h < 0)
            return x <= p ? playedColor : unplayedColor
        if (h > p)
            return x <= p ? playedColor : x <= h ? aheadColor : unplayedColor
        return x <= h ? playedColor : unplayedColor
    }

    function formatTime(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const h = Math.floor(total / 3600)
        const m = Math.floor((total % 3600) / 60)
        const s = total % 60
        const pad = s < 10 ? "0" + s : "" + s
        return h > 0 ? h + ":" + (m < 10 ? "0" : "") + m + ":" + pad : m + ":" + pad
    }

    onLevelsChanged: bars.requestPaint()
    onRatioChanged: bars.requestPaint()
    onHoverPxChanged: bars.requestPaint()
    onWaveStateChanged: bars.requestPaint()
    onWaveHeightChanged: bars.requestPaint()
    onMinBarChanged: bars.requestPaint()
    onPlayedColorChanged: bars.requestPaint()
    onUnplayedColorChanged: bars.requestPaint()
    onAheadColorChanged: bars.requestPaint()

    Item {
        id: plotArea
        anchors.left: parent.left
        anchors.right: times.left
        anchors.rightMargin: 16
        height: wave.waveHeight

        Canvas {
            id: bars
            width: wave.span
            height: parent.height
            onWidthChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const count = wave.levels.length
                const step = wave.barWidth + wave.barGap
                const p = wave.ratio * wave.span
                const h = wave.hoverPx
                for (let i = 0; i < count; ++i) {
                    const x = i * step
                    const level = wave.ready ? wave.levels[i] : 0
                    const barHeight = Math.max(wave.minBar, level * height)
                    ctx.fillStyle = wave.ready ? wave.barColor(x + wave.barWidth / 2, p, h) : wave.unplayedColor
                    ctx.beginPath()
                    ctx.roundedRect(x, (height - barHeight) / 2, wave.barWidth, barHeight, wave.barWidth / 2, wave.barWidth / 2)
                    ctx.fill()
                }
            }
        }

        Rectangle {
            visible: wave.ready
            width: wave.playheadWidth
            height: parent.height
            x: Math.max(0, Math.min(wave.span - width, wave.ratio * wave.span - width / 2))
            color: wave.playedColor
        }

        Text {
            visible: wave.waveState === "generating"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -16
            text: "Generating waveform · " + Math.round(wave.progress * 100) + "%"
            color: Qt.rgba(1, 1, 1, 0.7)
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            visible: wave.waveState === "unavailable"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -16
            spacing: 12

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: wave.message
                color: Qt.rgba(1, 1, 1, 0.8)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                kind: "ghost"
                text: "Retry"
                onClicked: wave.retryRequested()
            }
        }

        MouseArea {
            id: area
            objectName: "waveArea"
            x: 0
            width: wave.span
            height: parent.height
            enabled: wave.seekable && wave.ready
            hoverEnabled: true
            preventStealing: true
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.PointingHandCursor

            property var samples: []
            property bool silent: false
            property bool beyond: false
            property real pending: -1
            property real lastSeek: -1
            property double lastSeekTime: 0
            property double slowSince: 0
            readonly property real fastRatioPerSecond: 2000 / Math.max(1, wave.span)

            function clamp01(value) { return Math.max(0, Math.min(1, value)) }
            function speed(now) {
                const recent = samples.filter(item => now - item.t <= 60)
                if (recent.length < 2)
                    return 0
                const first = recent[0]
                const last = recent[recent.length - 1]
                return last.t > first.t ? Math.abs(last.r - first.r) / (last.t - first.t) * 1000 : 0
            }
            function doSeek(value, now) {
                lastSeek = value
                lastSeekTime = now
                wave.seekRequested(value)
            }
            function status(text) { wave.scrubStatus = text }
            function track(raw, now) {
                samples.push({t: now, r: raw})
                samples = samples.filter(item => now - item.t <= 200)
                pending = clamp01(raw)
                if (raw > 1) {
                    if (!beyond)
                        status("Scrub · beyond the end: silent, Next on release")
                    beyond = true
                    silent = true
                    return
                }
                beyond = false
                if (speed(now) > fastRatioPerSecond) {
                    if (!silent)
                        status("Scrub · fast movement: sound cut")
                    silent = true
                    slowSince = 0
                    return
                }
                if (!silent && now - lastSeekTime >= 100)
                    doSeek(pending, now)
            }

            onPressed: mouse => {
                const now = Date.now()
                const raw = mouse.x / wave.span
                samples = []
                silent = false
                beyond = false
                slowSince = 0
                lastSeek = -1
                lastSeekTime = 0
                status("Scrub · held")
                track(raw, now)
                if (raw <= 1)
                    doSeek(clamp01(raw), now)
                wave.playRequested()
            }
            onPositionChanged: mouse => { if (pressed) track(mouse.x / wave.span, Date.now()) }
            onReleased: mouse => {
                const raw = mouse.x / wave.span
                if (raw > 1) {
                    wave.nextRequested()
                    status("Scrub · released beyond the end: Next")
                } else {
                    if (clamp01(raw) !== lastSeek)
                        doSeek(clamp01(raw), Date.now())
                    wave.playRequested()
                    status("Scrub · released: playing")
                }
                silent = false
                beyond = false
            }
            onCanceled: { silent = false; beyond = false }

            Timer {
                interval: 20
                repeat: true
                running: area.pressed
                onTriggered: {
                    const now = Date.now()
                    if (area.beyond)
                        return
                    if (area.silent) {
                        if (area.speed(now) <= area.fastRatioPerSecond) {
                            if (area.slowSince === 0)
                                area.slowSince = now
                            else if (now - area.slowSince >= 80) {
                                area.doSeek(area.pending, now)
                                area.silent = false
                                area.slowSince = 0
                                area.status("Scrub · slowed down: sound resumes")
                            }
                        } else {
                            area.slowSince = 0
                        }
                        return
                    }
                    if (area.pending >= 0 && area.pending !== area.lastSeek && now - area.lastSeekTime >= 100)
                        area.doSeek(area.pending, now)
                }
            }
        }
    }

    Item {
        id: times
        anchors.right: parent.right
        width: wave.timeColumn
        height: wave.waveHeight

        Text {
            anchors.right: parent.right
            anchors.bottom: divider.top
            anchors.bottomMargin: 6
            text: wave.formatTime((wave.hoverRatio >= 0 ? wave.hoverRatio : wave.ratio) * wave.duration)
            color: Qt.rgba(1, 1, 1, 0.95)
            font.family: Theme.fontFamily
            font.pixelSize: 14
            font.features: { "tnum": 1 }
        }

        Rectangle {
            id: divider
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: 1
            color: Qt.rgba(1, 1, 1, 0.35)
        }

        Text {
            anchors.right: parent.right
            anchors.top: divider.bottom
            anchors.topMargin: 6
            text: wave.formatTime(wave.duration)
            color: Qt.rgba(1, 1, 1, 0.6)
            font.family: Theme.fontFamily
            font.pixelSize: 14
            font.features: { "tnum": 1 }
        }
    }
}
