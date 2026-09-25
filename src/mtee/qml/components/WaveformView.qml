import QtQuick
import Mtee

FocusScope {
    id: view

    required property var waveform
    required property var playback
    property real playheadRatio: 0

    implicitHeight: 116

    Canvas {
        id: canvas
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 84
        property var points: view.waveform.samples
        property real played: view.playheadRatio
        onPointsChanged: requestPaint()
        onPlayedChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
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
                ctx.lineWidth = Math.max(1, width / points.length * 0.64)
                ctx.stroke()
            }
            if (played >= 0 && played <= 1) {
                const x = played * width
                ctx.beginPath()
                ctx.moveTo(x, 0)
                ctx.lineTo(x, height)
                ctx.strokeStyle = Theme.textPrimary
                ctx.lineWidth = 1
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
}
