import QtQuick
import Mtee

// Content of the activity chosen in the activity bar.
Rectangle {
    id: sidebar

    required property var workspace
    signal resizeRequested(real delta)

    color: Theme.sidebar

    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.LeftButton
        onClicked: sidebar.workspace.clearSelection(sidebar.workspace.activeGroup)
    }

    Loader {
        anchors.fill: parent
        anchors.rightMargin: 1
        sourceComponent: sidebar.workspace.activity === "playlists" ? playlistsPane
            : sidebar.workspace.activity === "artists" ? artistsPane
            : sidebar.workspace.activity === "convert" ? convertPane
            : sidebar.workspace.activity === "tasks" ? tasksPane
            : sidebar.workspace.activity === "plugins" ? pluginsPane
            : sidebar.workspace.activity === "profile" ? profilePane
            : explorerPane
    }

    Component { id: explorerPane; ExplorerPane { workspace: sidebar.workspace } }
    Component { id: playlistsPane; PlaylistsPane { workspace: sidebar.workspace } }
    Component { id: artistsPane; ArtistManagerPane { workspace: sidebar.workspace } }
    Component { id: convertPane; ConvertPane { workspace: sidebar.workspace } }
    Component { id: tasksPane; TasksPane { workspace: sidebar.workspace } }
    Component {
        id: pluginsPane
        PlaceholderPane {
            title: "Plugins"
            icon: "plugins"
            message: "Plugins aren't available yet. This space is reserved for them."
        }
    }
    Component {
        id: profilePane
        PlaceholderPane {
            title: "Profile"
            icon: "profile"
            message: "Your profile isn't available yet. This space is reserved for it."
        }
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
