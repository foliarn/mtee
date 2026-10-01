import QtQuick
import Mtee

// Review prototype of MarqueeText (plan 100, C11): static when the text fits,
// otherwise scrolls to its end, pauses, returns and pauses again.
Item {
    id: marquee

    property string text: ""
    property color color: Theme.textPrimary
    property int pixelSize: 34
    property bool bold: true
    property real speed: 40
    property int pause: 2000
    readonly property real overflow: Math.max(0, label.implicitWidth - width)

    clip: true
    implicitHeight: label.implicitHeight

    function restart() {
        run.stop()
        label.x = 0
        if (overflow > 0 && width > 0)
            run.start()
    }

    onTextChanged: Qt.callLater(restart)
    onOverflowChanged: Qt.callLater(restart)
    onVisibleChanged: if (visible) Qt.callLater(restart)
    Component.onCompleted: Qt.callLater(restart)

    Text {
        id: label
        text: marquee.text
        color: marquee.color
        font.family: Theme.fontFamily
        font.pixelSize: marquee.pixelSize
        font.weight: marquee.bold ? Font.Bold : Font.Normal
    }

    SequentialAnimation {
        id: run
        loops: Animation.Infinite
        PauseAnimation { duration: marquee.pause }
        NumberAnimation { target: label; property: "x"; to: -marquee.overflow; duration: Math.max(1, marquee.overflow / marquee.speed * 1000) }
        PauseAnimation { duration: marquee.pause }
        NumberAnimation { target: label; property: "x"; to: 0; duration: Math.max(1, marquee.overflow / marquee.speed * 1000) }
    }
}
