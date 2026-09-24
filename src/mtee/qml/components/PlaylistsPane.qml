import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Invented playlists; their real behaviour arrives with plan 10.
Item {
    id: pane

    required property var workspace
    readonly property string activePlaylist: {
        const groups = workspace.groups
        if (groups.length === 0)
            return ""
        const parts = groups[workspace.activeGroup].active.split(":")
        return parts[0] === "playlist" ? parts[1] : ""
    }

    objectName: "playlistsPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Playlists"

        IconButton {
            icon: "plus"
            iconSize: 16
            width: 26
            height: 26
            tip: "New playlist"
            onClicked: pane.workspace.addToNewPlaylist([])
        }
    }

    ListView {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: pane.workspace.playlists
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: entry
            required property var modelData
            readonly property bool current: pane.activePlaylist === modelData.id

            width: ListView.view.width
            height: 56
            color: current ? Theme.selection : entryMouse.containsMouse ? Theme.surface : "transparent"

            CoverArt {
                id: art
                x: 16
                anchors.verticalCenter: parent.verticalCenter
                width: 40
                height: 40
                pattern: entry.modelData.cover
            }

            Column {
                anchors.left: art.right
                anchors.leftMargin: 12
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Text {
                    width: parent.width
                    text: entry.modelData.name
                    elide: Text.ElideRight
                    color: entry.current ? Theme.primary : Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    width: parent.width
                    text: "Playlist · " + entry.modelData.summary
                    elide: Text.ElideRight
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            MouseArea {
                id: entryMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: pane.workspace.openPlaylist(entry.modelData.id)
            }
        }
    }
}
