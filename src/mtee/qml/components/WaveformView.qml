import QtQuick
import Mtee

FocusScope {
    id: view

    required property var waveform
    required property var playback
    property real playheadRatio: 0
    readonly property real visibleDuration: 1 / waveform.zoomFactor

    implicitHeight: 116
    focus: true

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal)
            waveform.zoomIn()
        else if (event.key === Qt.Key_Minus)
            waveform.zoomOut()
        else if (event.key === Qt.Key_Left)
            waveform.pan(-0.1)
        else if (event.key === Qt.Key_Right)
            waveform.pan(0.1)
        else
            return
        event.accepted = true
    }

    Canvas {
        id: canvas
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 84
        property var points: view.waveform.samples
        property real played: view.playheadRatio
        property real start: view.waveform.viewStart
        property real windowSize: view.visibleDuration
        property int markerA: view.waveform.markerA
        property int markerB: view.waveform.markerB
        onPointsChanged: requestPaint()
        onPlayedChanged: requestPaint()
        onStartChanged: requestPaint()
        onMarkerAChanged: requestPaint()
        onMarkerBChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            const center = height / 2
            const localPlayhead = (played - start) / windowSize
            for (let i = 0; i < points.length; ++i) {
                const x = (i + 0.5) * width / points.length
                const low = points[i][0]
                const high = points[i][1]
                const y1 = center - high * center * 0.92
                const y2 = center - low * center * 0.92
                ctx.beginPath()
                ctx.moveTo(x, y1)
                ctx.lineTo(x, y2)
                ctx.strokeStyle = (i / points.length + start) < played
                    ? Theme.primary : Theme.selection
                ctx.lineWidth = Math.max(1, width / points.length * 0.64)
                ctx.stroke()
            }
            if (markerA >= 0) {
                const x = (markerA / view.waveform.durationUs - start) / windowSize * width
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height)
                ctx.strokeStyle = Theme.warning; ctx.lineWidth = 2; ctx.stroke()
            }
            if (markerB >= 0) {
                const x = (markerB / view.waveform.durationUs - start) / windowSize * width
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height)
                ctx.strokeStyle = Theme.warning; ctx.lineWidth = 2; ctx.stroke()
            }
            if (localPlayhead >= 0 && localPlayhead <= 1) {
                const x = localPlayhead * width
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height)
                ctx.strokeStyle = Theme.textPrimary; ctx.lineWidth = 1; ctx.stroke()
            }
        }

        Connections {
            target: view.waveform
            function onChanged() { canvas.requestPaint() }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: (event) => {
                if (event.button === Qt.RightButton)
                    view.waveform.clearLoop()
                else {
                    const ratio = view.waveform.viewStart
                        + event.x / width * view.visibleDuration
                    view.waveform.seekRatio(ratio)
                    view.forceActiveFocus()
                }
            }
            onWheel: (event) => {
                if (event.angleDelta.y > 0) view.waveform.zoomIn()
                else view.waveform.zoomOut()
                event.accepted = true
            }
        }
    }

    Row {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 26
        spacing: 6

        TextButton { text: "−"; implicitWidth: 28; implicitHeight: 26; kind: "ghost"; onClicked: view.waveform.zoomOut() }
        Text {
            width: 62; height: 26; verticalAlignment: Text.AlignVCenter
            text: Math.round(view.waveform.zoomFactor * 100) + "%"
            color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
        TextButton { text: "+"; implicitWidth: 28; implicitHeight: 26; kind: "ghost"; onClicked: view.waveform.zoomIn() }
        TextButton { text: "A"; implicitWidth: 28; implicitHeight: 26; kind: "ghost"; tip: "Set loop start at playhead"; onClicked: view.waveform.markLoopA() }
        TextButton { text: "B"; implicitWidth: 28; implicitHeight: 26; kind: "ghost"; tip: "Set loop end at playhead"; onClicked: view.waveform.markLoopB() }
        TextButton { text: "Clear loop"; implicitWidth: 78; implicitHeight: 26; kind: "ghost"; onClicked: view.waveform.clearLoop() }
        Item { width: 1; height: 1 }
        Text {
            width: Math.max(0, view.width - 290); height: 26; verticalAlignment: Text.AlignVCenter
            text: view.waveform.markerA < 0 ? "Click to seek · A/B sets loop at playhead"
                : view.waveform.markerB < 0 ? "Loop start set · move playback and set B"
                : "A/B loop active · right-click to clear"
            color: Theme.textMuted; elide: Text.ElideRight
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
    }
}
