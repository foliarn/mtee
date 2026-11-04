import QtQuick
import QtQuick.Controls.Basic

// A drop-down surface anchored under an item, for the header buttons (plan 130). It closes on Esc
// and on a click outside, stays inside the window with an 8 px margin, and scrolls when its
// content is taller than ``maxHeight``. Put the content in as children; give them explicit sizes.
Popup {
    id: popover

    // The item the popover hangs under; its right edge is the popover's right edge by default.
    property Item anchorItem: null
    property bool alignRight: true
    property int bodyWidth: 280
    property int maxHeight: 480
    readonly property int edgeMargin: 8
    default property alias data: body.data

    parent: Overlay.overlay
    padding: 8
    modal: true
    dim: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: bodyWidth + leftPadding + rightPadding
    height: Math.min(maxHeight, body.childrenRect.height + topPadding + bottomPadding)

    // A press outside closes the popover before the click of its own button arrives, so the click
    // must not open it again: ``toggle`` is what a button calls (HeaderButton + Popover pairs).
    // The popover is modal (and not dimmed): a press outside closes it and goes no further, so the
    // click on its own button cannot open it again at once. That makes the button a toggle.
    function toggle() {
        if (opened)
            close()
        else
            open()
    }

    function place() {
        const root = Overlay.overlay
        if (!root)
            return
        let px = 0
        let py = edgeMargin
        if (anchorItem) {
            const origin = anchorItem.mapToItem(root, 0, anchorItem.height)
            py = origin.y + 4
            px = alignRight ? origin.x + anchorItem.width - width : origin.x
        }
        x = Math.max(edgeMargin, Math.min(root.width - width - edgeMargin, px))
        y = Math.max(edgeMargin, Math.min(root.height - height - edgeMargin, py))
    }

    onAboutToShow: place()
    onWidthChanged: if (opened) place()
    onHeightChanged: if (opened) place()

    Overlay.modal: Item {}

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusWindow
        border.width: 1
        border.color: Theme.separator
    }

    contentItem: Flickable {
        id: flick
        clip: true
        contentWidth: width
        contentHeight: body.childrenRect.height
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}
        WheelScrollHandler { flickable: flick }

        Item {
            id: body
            width: flick.width
            height: childrenRect.height
        }
    }
}
