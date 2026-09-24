import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Folder tree: a click on a folder opens it in a tab, a click on a file selects
// it, a double click plays it. The folder of the active tab is highlighted.
Item {
    id: pane

    required property var workspace

    objectName: "explorerPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Explorer"

        IconButton {
            icon: "plus"
            iconSize: 16
            width: 26
            height: 26
            tip: "Add folder"
        }
    }

    ListView {
        id: tree
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: pane.workspace.explorerRows
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: row

            required property var modelData
            readonly property bool isFolder: modelData.kind === "folder"
            readonly property bool activeFolder: isFolder && pane.workspace.activeFolder === modelData.id
            readonly property bool selected: !isFolder && pane.workspace.selectedIds.indexOf(modelData.id) >= 0
            readonly property bool playing: !isFolder && pane.workspace.playingId === modelData.id

            width: tree.width
            height: Theme.treeRowHeight
            color: selected ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"

            Icon {
                id: chevron
                x: 8 + row.modelData.depth * 14
                anchors.verticalCenter: parent.verticalCenter
                visible: row.isFolder && row.modelData.hasChildren
                name: row.modelData.expanded ? "chevron-down" : "chevron-right"
                size: 16
                color: Theme.textSecondary
            }

            Text {
                anchors.left: chevron.right
                anchors.leftMargin: row.isFolder ? 4 : 6
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: row.modelData.name
                elide: Text.ElideRight
                color: row.activeFolder || row.playing ? Theme.primary
                    : row.isFolder ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.weight: row.modelData.depth === 0 ? Font.DemiBold : Font.Normal
            }

            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                onClicked: (event) => {
                    if (row.isFolder) {
                        const onChevron = event.x < chevron.x + chevron.width + 2
                        if (onChevron || row.modelData.depth === 0) {
                            pane.workspace.toggleFolder(row.modelData.id)
                        } else {
                            if (!row.modelData.expanded)
                                pane.workspace.toggleFolder(row.modelData.id)
                            pane.workspace.openFolder(row.modelData.id)
                        }
                    } else {
                        const track = pane.workspace.track(row.modelData.id)
                        pane.workspace.openFolder(track.folder)
                        pane.workspace.selectTrack(row.modelData.id, "single", [])
                    }
                }
                onDoubleClicked: {
                    if (!row.isFolder) {
                        const track = pane.workspace.track(row.modelData.id)
                        pane.workspace.playTrack(row.modelData.id, "folder:" + track.folder)
                    }
                }
            }
        }
    }
}
