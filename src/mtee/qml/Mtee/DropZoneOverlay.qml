import QtQuick
import "dropzones.js" as DropZones

// Placed over a center window (plan 130). While a drag of type tab or folder is over it, it draws
// the target zone (left, right, top, bottom, center) as a translucent accent rectangle. A drag
// source carries ``payload`` ({type: "tab" | "folder", ...}) and the drag keys "mtee-tab" or
// "mtee-folder". ``dropped`` carries the zone and the payload. Plan 131 wires it.
Item {
    id: overlay

    // The zones this window offers; the default keeps every child above the minimum size.
    property var allowed: DropZones.allowedFor(width, height, Theme.minCenterWindowWidth,
        Theme.minCenterWindowHeight, Theme.windowGap)
    property string zone: ""
    readonly property bool dragging: area.containsDrag
    signal dropped(string zone, var payload)

    function zoneAt(x, y, w, h, list) {
        return DropZones.zoneAt(x, y, w, h, list)
    }

    DropArea {
        id: area
        anchors.fill: parent
        keys: ["mtee-tab", "mtee-folder"]
        onPositionChanged: (drag) => overlay.zone = DropZones.zoneAt(drag.x, drag.y, width, height, overlay.allowed)
        onExited: overlay.zone = ""
        onDropped: (drop) => {
            const target = DropZones.zoneAt(drop.x, drop.y, width, height, overlay.allowed)
            overlay.zone = ""
            if (target.length > 0)
                overlay.dropped(target, drop.source.payload)
        }
    }

    Rectangle {
        objectName: "dropZoneRect"
        visible: area.containsDrag && overlay.zone.length > 0
        readonly property var box: DropZones.rectOf(overlay.zone, overlay.width, overlay.height)
        x: box.x
        y: box.y
        width: box.width
        height: box.height
        radius: Theme.radiusWindow
        color: Qt.rgba(0.776, 1, 0.102, 0.16)
        border.width: 2
        border.color: Theme.primary
    }
}
