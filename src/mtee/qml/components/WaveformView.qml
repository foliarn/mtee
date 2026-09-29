import QtQuick
import Mtee

FocusScope {
    id: view

    required property var waveform
    required property var playback

    readonly property real durationSeconds: Math.max(0, Number(playback.playbackDuration) || 0)
    readonly property real positionSeconds: Math.max(0, Number(playback.position) || 0)
    readonly property real playheadRatio: durationSeconds > 0
        ? Math.max(0, Math.min(1, positionSeconds / durationSeconds)) : 0
    readonly property var displayPoints: {
        const source = waveform.samples || []
        const budget = Math.max(1, Math.floor(width / 2))
        if (source.length <= budget)
            return source

        const points = []
        for (let bin = 0; bin < budget; ++bin) {
            const start = Math.floor(bin * source.length / budget)
            const end = Math.max(start + 1, Math.floor((bin + 1) * source.length / budget))
            let low = 1
            let high = -1
            for (let index = start; index < end; ++index) {
                low = Math.min(low, source[index][0])
                high = Math.max(high, source[index][1])
            }
            points.push([low, high])
        }
        return points
    }

    implicitHeight: 116

    Canvas {
        id: waveformCanvas
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 84
        property var points: view.displayPoints
        onPointsChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (points.length === 0 || width <= 0 || height <= 0)
                return
            const center = height / 2
            for (let i = 0; i < points.length; ++i) {
                const x = (i + 0.5) * width / points.length
                const low = points[i][0]
                const high = points[i][1]
                const y1 = center - high * center * 0.92
                const y2 = center - low * center * 0.92
                ctx.beginPath()
                ctx.moveTo(x, y1)
                ctx.lineTo(x, y2)
                ctx.strokeStyle = Theme.textSecondary
                ctx.lineWidth = Math.min(2, Math.max(1, width / points.length * 0.64))
                ctx.stroke()
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton
            onClicked: (event) => {
                view.waveform.seekRatio(event.x / width)
                view.forceActiveFocus()
            }
        }
    }

    Item {
        id: playedWaveformClip
        z: 1
        anchors.left: waveformCanvas.left
        anchors.top: waveformCanvas.top
        height: waveformCanvas.height
        width: playbackOverlay.played * waveformCanvas.width
        clip: true

        Canvas {
            id: playedWaveformCanvas
            width: waveformCanvas.width
            height: waveformCanvas.height
            property var points: view.displayPoints
            onPointsChanged: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                if (points.length === 0 || width <= 0 || height <= 0)
                    return
                const center = height / 2
                ctx.beginPath()
                for (let i = 0; i < points.length; ++i) {
                    const x = (i + 0.5) * width / points.length
                    const low = points[i][0]
                    const high = points[i][1]
                    const y1 = center - high * center * 0.92
                    const y2 = center - low * center * 0.92
                    ctx.moveTo(x, y1)
                    ctx.lineTo(x, y2)
                }
                ctx.strokeStyle = Theme.textMuted
                ctx.lineWidth = Math.min(2, Math.max(1, width / points.length * 0.64))
                ctx.stroke()
            }
        }
    }

    Canvas {
        id: playbackOverlay
        z: 2
        anchors.fill: waveformCanvas
        property real played: view.playheadRatio
        property real duration: view.durationSeconds
        onPlayedChanged: requestPaint()
        onDurationChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            if (duration <= 0 || width <= 0 || height <= 0)
                return

            const ratio = Math.max(0, Math.min(1, played))
            const playedWidth = ratio * width

            const lineX = Math.max(0.5, Math.min(width - 0.5, playedWidth))
            ctx.beginPath()
            ctx.moveTo(lineX, 0)
            ctx.lineTo(lineX, height)
            ctx.strokeStyle = Theme.textPrimary
            ctx.lineWidth = 1
            ctx.stroke()
        }
    }

    Rectangle {
        id: timeTag
        z: 3
        visible: view.durationSeconds > 0
        width: Math.min(view.width, timeLabel.implicitWidth + 12)
        height: 22
        readonly property real inset: Math.min(4, Math.max(0, (view.width - width) / 2))
        x: Math.max(inset, Math.min(view.width - width - inset,
                                    view.playheadRatio * view.width - width / 2))
        y: 4
        radius: 3
        color: Theme.surface
        border.width: 1
        border.color: Theme.separator

        Text {
            id: timeLabel
            anchors.centerIn: parent
            width: parent.width - 8
            text: view.formatTime(Math.min(view.positionSeconds, view.durationSeconds))
            color: Theme.textPrimary
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.features: { "tnum": 1 }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 26
        verticalAlignment: Text.AlignVCenter
        text: view.waveform.state === "generating" ? "Preparing waveform…"
            : view.waveform.error.length > 0 ? view.waveform.error : "Click waveform to seek"
        color: Theme.textMuted
        elide: Text.ElideRight
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    function formatTime(seconds) {
        const total = Math.max(0, Math.floor(Number(seconds) || 0))
        const hours = Math.floor(total / 3600)
        const minutes = Math.floor(total / 60) % 60
        const remaining = total % 60
        const secondsText = remaining < 10 ? "0" + remaining : String(remaining)
        if (hours > 0) {
            const minutesText = minutes < 10 ? "0" + minutes : String(minutes)
            return hours + ":" + minutesText + ":" + secondsText
        }
        return Math.floor(total / 60) + ":" + secondsText
    }
}
