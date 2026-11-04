import QtQuick
import QtQuick.Controls
import QtQuick.Window
import Mtee
import "components"
import "views"

// Frameless MTEE window: the frame (header, tool bars, windows, player bar), the dialogs, the
// toast, the native resize edges and the window shortcuts (components/AppShortcuts.qml).
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
