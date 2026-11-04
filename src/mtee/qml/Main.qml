import QtQuick
import QtQuick.Controls
import QtQuick.Window
import Mtee
import "components"
import "views"

// Frameless MTEE window: the frame (header, tool bars, windows, player bar), the dialogs, the
// native resize edges and the window shortcuts (components/AppShortcuts.qml).
Window {
    id: root

    objectName: "mteeWindow"
    property var ws: workspace
    readonly property bool maximized: visibility === Window.Maximized

    // Reference size 1440 × 900, reduced to fit a smaller or scaled screen.
    width: Math.max(minimumWidth, Math.min(1440, Screen.desktopAvailableWidth - 32))
    height: Math.max(minimumHeight, Math.min(900, Screen.desktopAvailableHeight - 32))
    minimumWidth: Theme.minWindowWidth
    minimumHeight: Theme.minWindowHeight
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "MTEE"
    color: Theme.chrome

    // The window comes back where it was closed (position, size, maximized), if it is still on a
    // screen. The size and place of the restored (not maximized) window are tracked as it moves.
    property rect normalGeometry: Qt.rect(0, 0, 0, 0)
    function noteGeometry() {
        if (visibility === Window.Windowed)
            normalGeometry = Qt.rect(x, y, width, height)
    }
    onXChanged: noteGeometry()
    onYChanged: noteGeometry()
    onWidthChanged: noteGeometry()
    onHeightChanged: noteGeometry()
    function onScreens(rect) {
        const cx = rect.x + rect.width / 2
        const cy = rect.y + rect.height / 2
        for (const screen of Qt.application.screens) {
            if (cx >= screen.virtualX && cx < screen.virtualX + screen.width
                    && cy >= screen.virtualY && cy < screen.virtualY + screen.height)
                return true
        }
        return false
    }
    function restoreGeometry() {
        const saved = typeof ws.savedWindow === "object" && ws.savedWindow ? ws.savedWindow : {}
        if (saved.width === undefined)
            return
        const rect = Qt.rect(saved.x, saved.y, Math.max(minimumWidth, saved.width), Math.max(minimumHeight, saved.height))
        if (onScreens(rect)) {
            x = rect.x
            y = rect.y
            width = rect.width
            height = rect.height
        }
        if (saved.maximized === true)
            visibility = Window.Maximized
    }
    function saveGeometry() {
        if (typeof ws.saveWindowGeometry !== "function")
            return
        noteGeometry()
        const r = normalGeometry.width > 0 ? normalGeometry : Qt.rect(x, y, width, height)
        ws.saveWindowGeometry(r.x, r.y, r.width, r.height, maximized)
    }
    Component.onCompleted: restoreGeometry()
    onClosing: saveGeometry()

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

    Loader {
        active: !shell.demoMode
        sourceComponent: Component { PluginDialogHost { workspace: root.ws } }
    }

    // The install warning and the refusal of the Plugins view: they open from any view, the demo too.
    PluginInstallDialogs { workspace: root.ws }

    AppFrame {
        id: frame
        anchors.fill: parent
        window: root
        workspace: root.ws
    }

    AppShortcuts {
        window: root
        workspace: root.ws
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

    RenameFileDialog {
        workspace: root.ws
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
}
