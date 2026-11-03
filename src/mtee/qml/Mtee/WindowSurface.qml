import QtQuick
import QtQuick.Shapes

// A rounded window of the frame (plan 130). Children go into the clipped content area; the four
// corners are masked with ``cornerColor`` (the colour behind the window, the frame by default)
// so a child never paints square corners over the rounded surface. ``focused`` draws a 1 px
// accent outline. The internal items are property values, not children, so that the default
// property sends only the caller's children to the content area.
Rectangle {
    id: surface

    property bool focused: false
    property int padding: 0
    // The colour seen around the window, painted in the four corners.
    property color cornerColor: Theme.chrome
    default property alias data: content.data
    readonly property Item contentArea: content

    radius: Theme.radiusWindow
    color: Theme.windowSurface

    readonly property Item contentHolder: Item {
        id: content
        parent: surface
        x: surface.padding
        y: surface.padding
        width: surface.width - 2 * surface.padding
        height: surface.height - 2 * surface.padding
        clip: true
    }

    // Everything between the outer rectangle and the rounded one: the four corner wedges.
    readonly property Item cornerMask: Shape {
        objectName: "windowSurfaceCorners"
        parent: surface
        width: surface.width
        height: surface.height
        z: 1000
        visible: surface.radius > 0
        enabled: false

        ShapePath {
            id: wedges
            readonly property real w: surface.width
            readonly property real h: surface.height
            readonly property real r: Math.min(surface.radius, Math.min(w, h) / 2)

            fillColor: surface.cornerColor
            strokeColor: "transparent"
            strokeWidth: 0
            fillRule: ShapePath.OddEvenFill

            startX: 0
            startY: 0
            PathLine { x: wedges.w; y: 0 }
            PathLine { x: wedges.w; y: wedges.h }
            PathLine { x: 0; y: wedges.h }
            PathLine { x: 0; y: 0 }

            PathMove { x: wedges.r; y: 0 }
            PathLine { x: wedges.w - wedges.r; y: 0 }
            PathArc { x: wedges.w; y: wedges.r; radiusX: wedges.r; radiusY: wedges.r }
            PathLine { x: wedges.w; y: wedges.h - wedges.r }
            PathArc { x: wedges.w - wedges.r; y: wedges.h; radiusX: wedges.r; radiusY: wedges.r }
            PathLine { x: wedges.r; y: wedges.h }
            PathArc { x: 0; y: wedges.h - wedges.r; radiusX: wedges.r; radiusY: wedges.r }
            PathLine { x: 0; y: wedges.r }
            PathArc { x: wedges.r; y: 0; radiusX: wedges.r; radiusY: wedges.r }
        }
    }

    readonly property Item outline: Rectangle {
        objectName: "windowSurfaceOutline"
        parent: surface
        width: surface.width
        height: surface.height
        z: 1001
        radius: surface.radius
        color: "transparent"
        border.width: 1
        border.color: Theme.primary
        visible: surface.focused
    }
}
