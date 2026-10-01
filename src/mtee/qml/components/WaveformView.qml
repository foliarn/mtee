import QtQuick
import Mtee

// Fullscreen waveform (plan 100): symmetric rounded bars drawn from the RMS levels of
// the waveform model, a thin playhead, hover colouring and two stacked times on the
// right. Hovering never moves the playhead or the sound.
FocusScope {
    id: view

    required property var waveform
    required property var playback

    // The playback engine's duration, else the one of the library metadata.
    readonly property real durationSeconds: Math.max(0,
        Number(playback.playbackDuration) || Number(playback.duration) || 0)
    readonly property real positionSeconds: Math.max(0, Number(playback.position) || 0)
    readonly property real playheadRatio: durationSeconds > 0
        ? Math.max(0, Math.min(1, positionSeconds / durationSeconds)) : 0
    readonly property bool interactive: playback.seekable === true && waveform.state === "ready"
    // Bar heights in [0, 1], one float32 per bar (see WaveformModel.levels).
    readonly property var levelValues: {
        const raw = waveform.levels
        return raw && raw.byteLength >= 4 ? new Float32Array(raw) : []
    }
    readonly property bool ready: waveform.state === "ready"
    readonly property int barWidth: Theme.waveBarWidth
    readonly property int barGap: Theme.waveBarGap
    readonly property int barCount: Math.max(1, Math.floor((plot.width + barGap) / (barWidth + barGap)))
    // Without a ready waveform, flat minimal bars fill the width.
    readonly property int drawCount: ready ? levelValues.length : barCount
    readonly property real span: drawCount * barWidth + Math.max(0, drawCount - 1) * barGap
    // Hovered position as a ratio of the drawn bars; -1 when the mouse is elsewhere.
    readonly property real hoverRatio: {
        if (!interactive || span <= 0 || !(area.containsMouse || area.pressed))
            return -1
        return Math.max(0, Math.min(1, area.mouseX / span))
    }
    readonly property real hoverPx: hoverRatio >= 0 ? hoverRatio * span : -1

    implicitHeight: Theme.waveHeight

    // Colour of the bar centred on ``x``: ``p`` is the playhead and ``h`` the hovered
    // abscissa (negative without hover), in pixels of the drawn bars.
    function barColor(x, p, h) {
        if (h < 0)
            return x <= p ? Theme.wavePlayed : Theme.waveUnplayed
        if (h > p)
            return x <= p ? Theme.wavePlayed : (x <= h ? Theme.waveHoverAhead : Theme.waveUnplayed)
        return x <= h ? Theme.wavePlayed : Theme.waveUnplayed
    }

    function formatTime(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const hours = Math.floor(total / 3600)
        const minutes = Math.floor((total % 3600) / 60)
        const secs = total % 60
        const pad = (secs < 10 ? "0" : "") + secs
        return hours > 0 ? hours + ":" + (minutes < 10 ? "0" : "") + minutes + ":" + pad
                         : minutes + ":" + pad
    }

    onBarCountChanged: barCountTimer.restart()
    onLevelValuesChanged: bars.requestPaint()
    onSpanChanged: bars.requestPaint()
    onReadyChanged: bars.requestPaint()
    onPlayheadRatioChanged: bars.requestPaint()
    onHoverPxChanged: bars.requestPaint()
    Component.onCompleted: view.waveform.setBarCount(view.barCount)

    Timer {
        id: barCountTimer
        interval: 50
        onTriggered: view.waveform.setBarCount(view.barCount)
    }

    Item {
        id: plot
        anchors.left: parent.left
        anchors.right: times.left
        anchors.rightMargin: 16
        height: Theme.waveHeight

        Canvas {
            id: bars
            objectName: "waveformBars"
            width: view.span
            height: parent.height
            onWidthChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                const count = view.drawCount
                const step = view.barWidth + view.barGap
                const ready = view.ready
                const p = view.playheadRatio * view.span
                const h = view.hoverPx
                for (let i = 0; i < count; ++i) {
                    const x = i * step
                    const barHeight = Math.max(Theme.waveMinBar, (ready ? view.levelValues[i] : 0) * height)
                    ctx.fillStyle = ready ? view.barColor(x + view.barWidth / 2, p, h) : Theme.waveUnplayed
                    ctx.beginPath()
                    ctx.roundedRect(x, (height - barHeight) / 2, view.barWidth, barHeight,
                                    view.barWidth / 2, view.barWidth / 2)
                    ctx.fill()
                }
            }
        }

        Rectangle {
            objectName: "wavePlayhead"
            visible: view.ready && view.levelValues.length > 0
            width: Theme.wavePlayheadWidth
            height: parent.height
            x: Math.max(0, Math.min(view.span - width, view.playheadRatio * view.span - width / 2))
            color: Theme.wavePlayed
        }

        Text {
            objectName: "waveformGenerating"
            visible: view.waveform.state === "generating"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -16
            text: "Generating waveform · " + Math.round((Number(view.waveform.progress) || 0) * 100) + "%"
            color: Qt.rgba(1, 1, 1, 0.7)
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            objectName: "waveformUnavailable"
            visible: view.waveform.state === "unavailable"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -16
            spacing: 12

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: view.waveform.error || "Waveform unavailable"
                color: Qt.rgba(1, 1, 1, 0.8)
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                objectName: "waveformRetry"
                kind: "ghost"
                text: "Retry"
                onClicked: view.waveform.retry()
            }
        }

        MouseArea {
            id: area
            objectName: "waveformArea"
            width: view.span
            height: parent.height
            enabled: view.interactive
            hoverEnabled: true
            preventStealing: true
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.PointingHandCursor

            // Ratios are not bounded: while the button is down the mouse may leave the
            // bars on either side, and the player needs to know which one.
            onPressed: (event) => {
                view.playback.scrubPress(event.x / view.span, view.span)
                view.forceActiveFocus()
            }
            onPositionChanged: (event) => {
                if (pressed)
                    view.playback.scrubMove(event.x / view.span)
            }
            onReleased: (event) => view.playback.scrubRelease(event.x / view.span)
            onCanceled: view.playback.scrubRelease(Math.max(0, Math.min(1, mouseX / view.span)))
        }
    }

    Item {
        id: times
        anchors.right: parent.right
        width: Theme.waveTimeColumn
        height: Theme.waveHeight

        Text {
            objectName: "waveformTimeTop"
            anchors.right: parent.right
            anchors.bottom: divider.top
            anchors.bottomMargin: 6
            text: view.formatTime((view.hoverRatio >= 0 ? view.hoverRatio : view.playheadRatio)
                                  * view.durationSeconds)
            color: Qt.rgba(1, 1, 1, 0.95)
            font.family: Theme.fontFamily
            font.pixelSize: 14
            font.features: { "tnum": 1 }
        }

        Rectangle {
            id: divider
            // 2px, so it is centred exactly on the bars (centred between two pixel rows).
            y: Math.round(parent.height / 2) - 1
            width: parent.width
            height: 2
            color: Qt.rgba(1, 1, 1, 0.35)
        }

        Text {
            objectName: "waveformTimeBottom"
            anchors.right: parent.right
            anchors.top: divider.bottom
            anchors.topMargin: 6
            text: view.formatTime(view.durationSeconds)
            color: Qt.rgba(1, 1, 1, 0.6)
            font.family: Theme.fontFamily
            font.pixelSize: 14
            font.features: { "tnum": 1 }
        }
    }
}
