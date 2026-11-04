import QtQuick
import Mtee
import "../views"

// The frame of the window (plan 131.5, docks in 131.6, responsive in 131.9): one background colour, the
// header on top, the tool bars on the left and the right (both as wide as the header is high), and the
// body between them. The body holds the two docks of the tool windows and the centre window, each a
// rounded window inset by ``Theme.windowGap`` from the bars, the header and the player bar at the foot.
//
// Responsive rules: at ``Theme.overlayDockWidth`` and above an open dock pushes the centre aside. Below
// it an open dock floats over the centre (elevated, with a shadow) and a click outside it closes it. Below
// ``Theme.singleWindowWidth`` the centre draws only its focused window (its tab strip has a switcher).
Item {
    id: frame

    required property var window
    required property var workspace

    readonly property bool overlayDocks: width < Theme.overlayDockWidth
    readonly property bool singleGroup: width < Theme.singleWindowWidth
    // The player bar is always shown at the foot of the frame (plan 131.8): the body stops above it.
    readonly property real footerReserve: Theme.playerBarHeight
    // Docks push the centre only when they are not floating.
    readonly property bool sidebarPushes: leftDock.shown && !overlayDocks
    readonly property bool rightPushes: rightDock.shown && !overlayDocks
    // True while a dock floats over the centre; a click outside or Esc closes the floating docks.
    readonly property bool floatingOpen: overlayDocks && (leftDock.shown || rightDock.shown)

    function closeFloatingDocks() {
        if (leftDock.shown)
            frame.workspace.toggleDock("left")
        if (rightDock.shown)
            frame.workspace.toggleDock("right")
    }

    // One colour for the whole frame: no separator lines between its parts.
    Rectangle {
        anchors.fill: parent
        color: Theme.chrome
    }

    HeaderBar {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        window: frame.window
        workspace: frame.workspace
        onSelectAllRequested: editor.selectAll()
    }

    ToolBar {
        id: leftBar
        objectName: "leftToolBar"
        side: "left"
        workspace: frame.workspace
        anchors.left: parent.left
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: frame.footerReserve
    }

    ToolBar {
        id: rightBar
        objectName: "rightToolBar"
        side: "right"
        workspace: frame.workspace
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: frame.footerReserve
    }

    // The body between the bars, inset by the window gap on every side.
    Item {
        id: body
        objectName: "mainBody"
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: frame.footerReserve
        anchors.left: leftBar.right
        anchors.right: rightBar.left

        Item {
            id: main
            objectName: "mainArea"
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.margins: Theme.windowGap
            // A pushing dock takes its width and one gap beside the body's own inset.
            anchors.left: parent.left
            anchors.leftMargin: frame.sidebarPushes ? leftDock.width + 2 * Theme.windowGap : Theme.windowGap
            anchors.right: parent.right
            anchors.rightMargin: frame.rightPushes ? rightDock.width + 2 * Theme.windowGap : Theme.windowGap

            // The centre windows are the tree's own rounded windows (plan 131.7): no frame around them.
            EditorArea {
                id: editor
                anchors.fill: parent
                visible: !frame.workspace.fullscreen
                workspace: frame.workspace
                singleGroup: frame.singleGroup
                bottomInset: 0
            }

            FullscreenPlayer {
                anchors.fill: parent
                visible: frame.workspace.fullscreen
                workspace: frame.workspace
            }
        }

        // While a dock floats, a click on the centre closes the floating docks (plan 131.9).
        MouseArea {
            objectName: "floatingDismiss"
            anchors.fill: main
            visible: frame.floatingOpen
            onClicked: frame.closeFloatingDocks()
        }

        // The left dock: the tool windows of the left side (plan 131.6).
        Dock {
            id: leftDock
            objectName: "leftDock"
            side: "left"
            workspace: frame.workspace
            floating: frame.overlayDocks
            bodyWidth: body.width
            z: 2
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.margins: Theme.windowGap
        }

        // The right dock: the tool windows of the right side (Info, Queue, History).
        Dock {
            id: rightDock
            objectName: "rightPanel"
            side: "right"
            workspace: frame.workspace
            floating: frame.overlayDocks
            bodyWidth: body.width
            z: 2
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.margins: Theme.windowGap
        }
    }

    // The player: the full-width footer of the frame (decision U11).
    PlayerBar {
        id: playerBar
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        workspace: frame.workspace
    }
}
