import QtQuick

// The hit area across the gap between two windows (plan 130). It draws nothing at rest; on hover
// or drag a 2 px accent line shows. ``orientation`` is the way the windows sit: Qt.Horizontal for
// windows side by side (a vertical strip, dragged left and right), Qt.Vertical for windows
// stacked. ``dragged`` carries the distance since the press, in pixels along the drag axis.
Item {
    id: handle

    property int orientation: Qt.Horizontal
    readonly property bool vertical: orientation === Qt.Vertical
    readonly property bool active: mouse.containsMouse || mouse.pressed
    readonly property int thickness: Theme.windowGap + 4
    signal dragged(real delta)
    signal released()
    signal doubleClicked()

    implicitWidth: vertical ? 0 : thickness
    implicitHeight: vertical ? thickness : 0

    Rectangle {
        objectName: "splitHandleLine"
        anchors.centerIn: parent
        width: handle.vertical ? parent.width : 2
        height: handle.vertical ? 2 : parent.height
        color: Theme.primary
        visible: handle.active
    }

    MouseArea {
        id: mouse
        property real origin: 0
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        cursorShape: handle.vertical ? Qt.SizeVerCursor : Qt.SizeHorCursor

        function axis(x, y) {
            const global = mapToItem(null, x, y)
            return handle.vertical ? global.y : global.x
        }

        onPressed: (event) => origin = axis(event.x, event.y)
        onPositionChanged: (event) => {
            if (pressed)
                handle.dragged(axis(event.x, event.y) - origin)
        }
        onReleased: handle.released()
        onDoubleClicked: handle.doubleClicked()
    }
}
