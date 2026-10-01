import QtQuick
import Mtee

// Single-line text that scrolls when it does not fit: it moves to its end, pauses,
// returns to the start and pauses again. It restarts whenever the text changes.
Item {
    id: marquee

    property string text: ""
    property color color: Theme.textPrimary
    property int pixelSize: Theme.fontSizeBody
    property bool bold: false
    property real speed: Theme.fsMarqueeSpeed
    property int pause: Theme.fsMarqueePause
    readonly property real overflow: Math.max(0, label.implicitWidth - width)
    readonly property bool scrolling: run.running

    clip: true
    implicitHeight: label.implicitHeight

    function restart() {
        run.stop()
        label.x = 0
        if (overflow > 0 && width > 0 && visible)
            run.start()
    }

    onTextChanged: Qt.callLater(restart)
    onOverflowChanged: Qt.callLater(restart)
    onVisibleChanged: Qt.callLater(restart)
    Component.onCompleted: Qt.callLater(restart)

    Text {
        id: label
        objectName: "marqueeLabel"
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
        NumberAnimation {
            target: label
            property: "x"
            to: -marquee.overflow
            duration: Math.max(1, marquee.overflow / marquee.speed * 1000)
        }
        PauseAnimation { duration: marquee.pause }
        NumberAnimation {
            target: label
            property: "x"
            to: 0
            duration: Math.max(1, marquee.overflow / marquee.speed * 1000)
        }
    }
}
