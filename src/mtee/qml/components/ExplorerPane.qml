import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
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
            enabled: typeof pane.workspace.addRoot === "function"
            onClicked: folderPicker.open()
        }
    }

    FolderDialog {
        id: folderPicker
        title: "Add a music folder"
        onAccepted: pane.workspace.addRoot(selectedFolder.toString())
    }

    ListView {
        id: tree
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        model: typeof pane.workspace.folderTreeModel === "object"
            ? pane.workspace.folderTreeModel : pane.workspace.explorerRows
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: row

            required property var modelData
            readonly property bool isFolder: modelData.kind === "folder"
            readonly property bool activeFolder: isFolder && pane.workspace.activeFolder === modelData.id
            readonly property bool selected: !isFolder && pane.workspace.selectedIds.indexOf(modelData.id) >= 0
            readonly property bool playing: !isFolder && pane.workspace.playingId === modelData.id
            readonly property string availability: isFolder ? (modelData.availability || "") : (modelData.status || "")

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
                id: folderName
                anchors.left: chevron.right
                anchors.leftMargin: row.isFolder ? 4 : 6
                anchors.right: parent.right
                anchors.rightMargin: statusLabel.visible ? statusLabel.implicitWidth + 16 : 8
                anchors.verticalCenter: parent.verticalCenter
                text: row.modelData.name
                elide: Text.ElideRight
                color: row.activeFolder || row.playing ? Theme.primary
                    : row.isFolder ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.weight: row.modelData.depth === 0 ? Font.DemiBold : Font.Normal
            }

            Text {
                id: statusLabel
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                visible: row.isFolder && row.availability !== "" && row.availability !== "available"
                text: row.availability === "scanning" ? "Scanning…"
                    : row.availability === "unavailable" ? "Unavailable" : "Partial"
                color: row.availability === "unavailable" ? Theme.danger : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton
                onClicked: (event) => {
                    if (row.isFolder) {
                        const onChevron = event.x < chevron.x + chevron.width + 2
                        if (onChevron) {
                            pane.workspace.toggleFolder(row.modelData.id)
                        } else {
                            if (!row.modelData.expanded)
                                pane.workspace.toggleFolder(row.modelData.id)
                            pane.workspace.openFolder(row.modelData.id)
                        }
                    } else {
                        pane.workspace.openFolder(row.modelData.folder)
                        pane.workspace.selectTrack(row.modelData.id, "single", [])
                    }
                }
                onDoubleClicked: {
                    if (!row.isFolder) {
                        pane.workspace.playTrack(row.modelData.id, row.modelData.folder)
                    } else {
                        pane.workspace.openFolder(row.modelData.id)
                    }
                }
            }
        }
    }
}
