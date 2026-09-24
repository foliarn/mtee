import QtQuick
import Mtee

// Placeholder for the waveform of plan 08: deterministic bars derived from the
// track id, played part in the primary colour. A click seeks.
Item {
    id: wave

    property string seed: ""
    property real ratio: 0
    readonly property int barWidth: 3
    readonly property int barGap: 2
    readonly property int count: Math.max(1, Math.floor(width / (barWidth + barGap)))
    signal seekRequested(real ratio)

    function level(index) {
        let hash = 7
        for (let i = 0; i < seed.length; ++i)
            hash = (hash * 31 + seed.charCodeAt(i)) % 100003
        const x = index / count
        const envelope = 0.35 + 0.65 * Math.sin(Math.PI * Math.min(1, x * 1.15))
        const noise = Math.abs(Math.sin((index + 1) * 12.9898 + hash * 0.017)) * 0.55 + 0.45
        return Math.max(0.08, Math.min(1, envelope * noise))
    }

    Row {
        anchors.verticalCenter: parent.verticalCenter
        spacing: wave.barGap

        Repeater {
            model: wave.count
            delegate: Rectangle {
                required property int index
                width: wave.barWidth
                height: Math.round(wave.height * wave.level(index))
                anchors.verticalCenter: parent.verticalCenter
                color: index / wave.count <= wave.ratio ? Theme.primary
                    : waveMouse.containsMouse ? Theme.textMuted : Theme.selection
            }
        }
    }

    MouseArea {
        id: waveMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: (event) => wave.seekRequested(Math.max(0, Math.min(1, event.x / width)))
    }
}
