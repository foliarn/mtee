import QtQuick

// Thin horizontal slider used for playback position and volume. The square
// handle appears on hover or while dragging.
Item {
    id: slider

    property real from: 0
    property real to: 1
    property real value: 0
    property color fillColor: Theme.primary
    property int trackHeight: 4
    readonly property bool dragging: mouse.pressed
    readonly property real ratio: to > from ? Math.max(0, Math.min(1, (displayed - from) / (to - from))) : 0
    property real dragValue: 0
    readonly property real displayed: dragging ? dragValue : value
    signal moved(real value)

    implicitWidth: 120
    implicitHeight: 16

    function valueAt(x) {
        const ratio = Math.max(0, Math.min(1, x / width))
        return from + ratio * (to - from)
    }

    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: slider.trackHeight
        radius: height / 2
        color: Theme.selection

        Rectangle {
            width: parent.width * slider.ratio
            height: parent.height
            radius: height / 2
            color: mouse.containsMouse || slider.dragging ? slider.fillColor : Qt.lighter(Theme.textSecondary, 1.2)
        }
    }

    Rectangle {
        visible: mouse.containsMouse || slider.dragging
        width: 10
        height: 10
        x: Math.max(0, Math.min(slider.width - width, slider.width * slider.ratio - width / 2))
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.textPrimary
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        anchors.topMargin: -4
        anchors.bottomMargin: -4
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        preventStealing: true
        onPressed: (event) => slider.dragValue = slider.valueAt(event.x)
        onPositionChanged: (event) => { if (pressed) slider.dragValue = slider.valueAt(event.x) }
        onReleased: (event) => slider.moved(slider.valueAt(event.x))
    }
}
