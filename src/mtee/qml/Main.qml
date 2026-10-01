import QtQuick
import QtQuick.Controls
import QtQuick.Window
import Mtee
import "components"
import "views"

// Frameless MTEE window: title bar, activity bar, sidebar, editor groups,
// right panel and the floating player island (PLAN.md §3, revision 2).
Window {
    id: root

    objectName: "mteeWindow"
    property var ws: workspace
    readonly property bool maximized: visibility === Window.Maximized
    readonly property bool compactSidebar: width < Theme.compactSidebarWidth
    readonly property bool singleGroup: width < Theme.singleGroupWidth
    readonly property bool islandVisible: ws.playingId.length > 0 && ws.islandEnabled
    property int sidebarWidth: shell.demoMode ? Theme.sidebarWidth : root.ws.sidebarWidth
    property int rightPanelWidth: shell.demoMode ? Theme.rightPanelWidth : root.ws.rightPanelWidth

    onSidebarWidthChanged: if (!shell.demoMode && sidebarWidth !== root.ws.sidebarWidth) root.ws.setSidebarWidth(sidebarWidth)
    onRightPanelWidthChanged: if (!shell.demoMode && rightPanelWidth !== root.ws.rightPanelWidth) root.ws.setRightPanelWidth(rightPanelWidth)

    // Reference size 1440 × 900, reduced to fit a smaller or scaled screen.
    width: Math.max(minimumWidth, Math.min(1440, Screen.desktopAvailableWidth - 32))
    height: Math.max(minimumHeight, Math.min(900, Screen.desktopAvailableHeight - 32))
    minimumWidth: 880
    minimumHeight: 600
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "MTEE"
    color: Theme.chrome

    // Below the compact width the sidebar folds away; reopened, it overlays
    // the editor until a click outside closes it.
    onCompactSidebarChanged: if (compactSidebar) ws.setSidebarVisible(false)
    Component.onCompleted: if (compactSidebar) ws.setSidebarVisible(false)

    // The Queue list of the fullscreen player keeps its own arrow keys.
    function queueListFocused() {
        const focused = root.activeFocusItem
        return focused !== null && focused !== undefined && focused.objectName === "fullscreenQueueList"
    }

    function textInputFocused() {
        const focused = root.activeFocusItem
        return focused !== null && focused !== undefined
            && (focused.objectName === "folderSearchField"
                || focused.objectName === "fieldEditorInput"
                || focused instanceof TextInput
                || focused instanceof TextEdit)
    }

    Timer {
        interval: 250
        repeat: true
        running: shell.demoMode && root.ws.isPlaying
        onTriggered: root.ws.tick(0.25)
    }

    Loader {
        active: !shell.demoMode
        sourceComponent: Component { PlaylistDialogs { workspace: root.ws } }
    }

    TitleBar {
        id: titleBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        window: root
        workspace: root.ws
        onSelectAllRequested: editor.selectAll()
    }

    Item {
        id: body
        anchors.top: titleBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        // The player bar spans the window under every pane.
        readonly property real playerReserve: root.islandVisible ? Theme.islandHeight : 0

        ActivityBar {
            id: activityBar
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: body.playerReserve
            workspace: root.ws
        }

        Item {
            id: main
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: body.playerReserve
            anchors.left: activityBar.right
            anchors.leftMargin: sidebar.visible && !root.compactSidebar ? sidebar.width : 0
            anchors.right: parent.right
            anchors.rightMargin: rightPanel.visible ? rightPanel.width : 0

            EditorArea {
                id: editor
                anchors.fill: parent
                visible: !root.ws.fullscreen
                workspace: root.ws
                singleGroup: root.singleGroup
                bottomInset: 0
            }

            FullscreenPlayer {
                anchors.fill: parent
                visible: root.ws.fullscreen
                workspace: root.ws
            }
        }

        PlayerIsland {
            id: island
            visible: root.islandVisible
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            workspace: root.ws
        }

        MouseArea {
            anchors.fill: main
            visible: root.compactSidebar && sidebar.visible
            onClicked: root.ws.setSidebarVisible(false)
        }

        SideBar {
            id: sidebar
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: body.playerReserve
            anchors.left: activityBar.right
            width: root.sidebarWidth
            visible: root.ws.sidebarVisible && !root.ws.fullscreen
            workspace: root.ws
            onResizeRequested: (delta) => root.sidebarWidth = Math.max(180, Math.min(420, root.sidebarWidth + delta))
        }

        RightPanel {
            id: rightPanel
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: body.playerReserve
            anchors.right: parent.right
            width: root.rightPanelWidth
            visible: root.ws.rightPanelVisible && !root.ws.fullscreen
            workspace: root.ws
            bottomInset: 0
            onResizeRequested: (delta) => root.rightPanelWidth = Math.max(260, Math.min(480, root.rightPanelWidth + delta))
        }
    }

    Rectangle {
        id: statusToast
        visible: !shell.demoMode && root.ws.message.length > 0
        z: 90
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        width: Math.min(560, parent.width - 48)
        height: 42
        color: Theme.surface
        border.width: 1
        border.color: Theme.separator

        Text {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            verticalAlignment: Text.AlignVCenter
            text: root.ws.message
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Timer {
            interval: 5000
            running: statusToast.visible
            onTriggered: root.ws.clearMessage()
        }
    }

    Loader {
        id: trashDialog
        active: !shell.demoMode
        sourceComponent: Component {
            TrashDialog {
                trashModel: root.ws.trashModel
            }
        }
    }

    // One pixel frame so the window stays distinct from what lies behind it.
    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: root.maximized ? 0 : 1
        border.color: Theme.separator
        z: 100
    }

    // Resize handles when the platform does not give native edges.
    Repeater {
        model: windowFrame.native || root.maximized ? [] : [
            { "edges": Qt.LeftEdge, "x": 0, "y": 6, "w": 6, "h": -12, "cursor": Qt.SizeHorCursor },
            { "edges": Qt.RightEdge, "x": -6, "y": 6, "w": 6, "h": -12, "cursor": Qt.SizeHorCursor },
            { "edges": Qt.TopEdge, "x": 6, "y": 0, "w": -12, "h": 4, "cursor": Qt.SizeVerCursor },
            { "edges": Qt.BottomEdge, "x": 6, "y": -6, "w": -12, "h": 6, "cursor": Qt.SizeVerCursor },
            { "edges": Qt.BottomEdge | Qt.RightEdge, "x": -8, "y": -8, "w": 8, "h": 8, "cursor": Qt.SizeFDiagCursor },
            { "edges": Qt.BottomEdge | Qt.LeftEdge, "x": 0, "y": -8, "w": 8, "h": 8, "cursor": Qt.SizeBDiagCursor }
        ]

        delegate: MouseArea {
            required property var modelData
            z: 101
            x: modelData.x < 0 ? root.width + modelData.x : modelData.x
            y: modelData.y < 0 ? root.height + modelData.y : modelData.y
            width: modelData.w <= 0 ? root.width + modelData.w : modelData.w
            height: modelData.h <= 0 ? root.height + modelData.h : modelData.h
            cursorShape: modelData.cursor
            onPressed: root.startSystemResize(modelData.edges)
        }
    }

    Shortcut {
        sequence: "Space"
        autoRepeat: false
        enabled: root.active && root.ws.playingId.length > 0 && !root.textInputFocused()
        onActivated: root.ws.togglePlay()
    }
    Shortcut { sequence: "Ctrl+I"; enabled: !root.textInputFocused(); onActivated: root.ws.toggleRightPanel("info") }
    Shortcut { sequence: "Ctrl+B"; enabled: !root.textInputFocused(); onActivated: root.ws.toggleSidebar() }
    Shortcut { sequence: "Ctrl+Shift+E"; enabled: !root.textInputFocused(); onActivated: root.ws.setActivity("explorer") }
    Shortcut { sequence: "Ctrl+\\"; enabled: !root.textInputFocused(); onActivated: root.ws.toggleSplit() }
    Shortcut { sequence: "Ctrl+,"; enabled: !root.textInputFocused(); onActivated: root.ws.openSettings() }
    Shortcut { sequence: "Ctrl+Right"; enabled: !root.textInputFocused(); onActivated: root.ws.next() }
    Shortcut { sequence: "Ctrl+Left"; enabled: !root.textInputFocused(); onActivated: root.ws.previous() }
    Shortcut { sequence: "Ctrl+Z"; enabled: !root.textInputFocused(); onActivated: root.ws.undoSave() }
    Shortcut {
        sequence: "Del"
        enabled: !shell.demoMode && root.ws.activity === "explorer" && root.ws.selectedIds.length > 0
            && !root.textInputFocused()
        onActivated: root.ws.trashModel.request_recycle(root.ws.selectedIds)
    }
    Shortcut { sequence: "F11"; onActivated: root.ws.setFullscreen(!root.ws.fullscreen) }
    // Fullscreen pages: the page keys never reach a text field.
    Shortcut {
        sequences: ["PgDown", "Down"]
        enabled: root.ws.fullscreen && root.ws.playingId.length > 0 && !root.textInputFocused()
            && !root.queueListFocused()
        onActivated: root.ws.setFullscreenPage(1)
    }
    Shortcut {
        sequences: ["PgUp", "Up"]
        enabled: root.ws.fullscreen && root.ws.playingId.length > 0 && !root.textInputFocused()
            && !root.queueListFocused()
        onActivated: root.ws.setFullscreenPage(0)
    }
    Shortcut {
        sequence: "Esc"
        enabled: root.ws.fullscreen
        onActivated: root.ws.setFullscreen(false)
    }
}
