import QtQuick
import Mtee

// Content of the activity chosen in the activity bar.
Rectangle {
    id: sidebar

    required property var workspace
    signal resizeRequested(real delta)

    color: Theme.sidebar

    Loader {
        anchors.fill: parent
        anchors.rightMargin: 1
        sourceComponent: sidebar.workspace.activity === "playlists" ? playlistsPane
            : sidebar.workspace.activity === "convert" ? convertPane
            : sidebar.workspace.activity === "tasks" ? tasksPane
            : sidebar.workspace.activity === "plugins" ? pluginsPane
            : explorerPane
    }

    Component { id: explorerPane; ExplorerPane { workspace: sidebar.workspace } }
    Component { id: playlistsPane; PlaylistsPane { workspace: sidebar.workspace } }
    Component { id: convertPane; ConvertPane { workspace: sidebar.workspace } }
    Component { id: tasksPane; TasksPane { workspace: sidebar.workspace } }
    Component {
        id: pluginsPane
        PluginsPane { workspace: sidebar.workspace }
    }

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.separator
        opacity: 0.6
    }

    MouseArea {
        id: resizer
        property real pressX: 0
        anchors.right: parent.right
        anchors.rightMargin: -3
        width: 6
        height: parent.height
        cursorShape: Qt.SizeHorCursor
        onPressed: (event) => pressX = event.x
        onPositionChanged: (event) => { if (pressed) sidebar.resizeRequested(event.x - pressX) }
    }
}
