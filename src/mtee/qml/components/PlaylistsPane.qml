import QtQuick
import QtQuick.Controls.Basic
import Mtee

Item {
    id: pane
    required property var workspace
    readonly property bool live: typeof workspace.playlistModel !== "undefined"
    readonly property var playlistsModel: live ? workspace.playlistModel : null
    readonly property string activePlaylist: workspace.groups.length ? workspace.groups[workspace.activeGroup].active.split(":")[1] || "" : ""
    property var contextEntry: ({})
    objectName: "playlistsPane"
    PaneHeader {
        id: header
        width: parent.width
        title: "Playlists"
        IconButton { id: plus; objectName: "playlistsPlusButton"; icon: "plus"; iconSize: 16; width: 26; height: 26; tip: "Create or import playlist"; onClicked: creation.popup(plus, 0, plus.height) }
    }
    AppMenu {
        id: creation
        objectName: "playlistCreationMenu"
        AppMenuItem { objectName: "newPlaylistMenuItem"; text: "New playlist"; onTriggered: pane.workspace.addToNewPlaylist([]) }
        AppMenuItem { objectName: "newFolderMenuItem"; text: "New folder"; visible: pane.live; onTriggered: pane.playlistsModel.requestUI("folder", "", []) }
        AppMenuItem { objectName: "resumeImportMenuItem"; text: "Resume interrupted import…"; visible: pane.live && pane.playlistsModel.pendingImports.length > 0; height: visible ? 28 : 0; implicitHeight: visible ? 28 : 0; onTriggered: pane.playlistsModel.requestUI("resume", "", []) }
        AppMenuItem { objectName: "importPlaylistMenuItem"; text: "Import playlist…"; visible: pane.live; onTriggered: pane.playlistsModel.requestUI("import", "", []) }
    }
    ListView {
        id: tree
        anchors.top: header.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: pane.live ? pane.playlistsModel.tree : pane.workspace.playlists
        ScrollBar.vertical: ThinScrollBar {}
        DropArea {
            anchors.fill: parent
            keys: ["mtee-playlist-node"]
            onDropped: drop => { if (drop.source) pane.playlistsModel.move(drop.source.nodeId, "", drop.source.nodeIsFolder, "") }
        }
        delegate: Rectangle {
            id: entry
            objectName: "playlistNode_" + modelData.id
            required property var modelData
            readonly property bool folder: modelData.kind === "folder"
            readonly property bool current: !folder && pane.activePlaylist === modelData.id
            property bool trackDropActive: false
            property string nodeId: modelData.id
            property bool nodeIsFolder: folder
            width: ListView.view.width; height: folder ? 40 : 56
            color: drop.containsDrag ? Theme.selection : current ? Theme.selection : hit.containsMouse ? Theme.surface : "transparent"
            border.width: trackDropActive ? 2 : 0
            border.color: Theme.primary
            Item {
                id: nodeProxy
                width: 1; height: 1
                Drag.active: nodeDrag.active; Drag.source: entry
                Drag.keys: ["mtee-playlist-node"]; Drag.supportedActions: Qt.MoveAction
            }
            DragHandler {
                id: nodeDrag; target: null; enabled: pane.live && entry.nodeId !== "liked"
                onTranslationChanged: { nodeProxy.x = centroid.position.x; nodeProxy.y = centroid.position.y }
                onActiveChanged: { if (active) { nodeProxy.x = centroid.position.x; nodeProxy.y = centroid.position.y } else nodeProxy.Drag.drop() }
            }
            Icon { id: folderIcon; visible: entry.folder; x: 14 + (entry.modelData.depth || 0) * 16; anchors.verticalCenter: parent.verticalCenter; name: entry.modelData.expanded ? "chevron-down" : "chevron-right"; size: 14; color: Theme.textSecondary }
            PlaylistCover { id: art; visible: !entry.folder; x: 14 + (entry.modelData.depth || 0) * 16; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; source: entry.modelData.coverUrl || ""; covers: entry.modelData.covers || [] }
            Column {
                x: entry.folder ? folderIcon.x + 24 : art.x + 52
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - x - 32; spacing: 3
                Text { width: parent.width; text: entry.modelData.name; elide: Text.ElideRight; color: entry.current ? Theme.primary : Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 15 }
                Text { visible: !entry.folder; width: parent.width; text: entry.modelData.summary || ""; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            }
            Icon { visible: entry.modelData.pinned || false; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; name: "pin"; size: 14; color: Theme.primary }
            MouseArea {
                id: hit; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: event => {
                    if (event.button === Qt.RightButton && !entry.folder) { pane.contextEntry = entry.modelData; context.popup(entry, event.x, event.y) }
                    else if (entry.folder) pane.playlistsModel.toggleFolder(entry.modelData.id)
                    else pane.workspace.openPlaylist(entry.modelData.id)
                }
            }
            DropArea {
                id: drop; anchors.fill: parent; keys: ["mtee-playlist-node", "mtee-tracks"]
                onEntered: event => {
                    entry.trackDropActive = !!(pane.live && event.source && event.source.dragCanAdd
                        && !entry.folder && entry.nodeId !== "liked")
                }
                onExited: entry.trackDropActive = false
                onDropped: event => {
                    entry.trackDropActive = false
                    if (!event.source || !pane.live) return
                    if (event.source.dragCanAdd && !entry.folder && entry.nodeId !== "liked") pane.playlistsModel.add(entry.nodeId, event.source.dragTrackIds)
                    else if (event.source.nodeId !== undefined && entry.nodeId !== "liked") pane.playlistsModel.move(event.source.nodeId, entry.folder ? entry.nodeId : entry.modelData.folder || "", event.source.nodeIsFolder, entry.folder ? "" : entry.nodeId)
                }
            }
        }
    }
    AppMenu {
        id: context
        AppMenuItem { objectName: "enqueuePlaylistAction"; text: "Add to queue"; visible: pane.contextEntry.kind !== "folder"; onTriggered: pane.workspace.enqueuePlaylist(pane.contextEntry.id) }
        AppMenuItem { text: "Edit playlist"; visible: pane.contextEntry.kind !== "folder"; onTriggered: pane.playlistsModel.requestUI("edit", pane.contextEntry.id, []) }
        AppMenuItem { text: pane.contextEntry.pinned ? "Unpin" : "Pin playlist"; visible: pane.contextEntry.kind !== "folder"; onTriggered: pane.playlistsModel.pin(pane.contextEntry.id, !pane.contextEntry.pinned) }
        AppMenuItem { text: "Create a copy"; visible: pane.contextEntry.kind !== "folder"; onTriggered: pane.playlistsModel.duplicate(pane.contextEntry.id) }
        AppMenuItem { text: "Export playlist…"; visible: pane.contextEntry.kind !== "folder"; onTriggered: pane.playlistsModel.requestUI("export", pane.contextEntry.id, []) }
        AppMenuItem { text: "New playlist here"; visible: pane.contextEntry.kind === "folder"; onTriggered: pane.playlistsModel.createUntitled(pane.contextEntry.id, []) }
        AppMenuItem { text: "New subfolder"; visible: pane.contextEntry.kind === "folder"; onTriggered: pane.playlistsModel.requestUI("folder", pane.contextEntry.id, []) }
        AppMenuItem { text: "Rename folder"; visible: pane.contextEntry.kind === "folder"; onTriggered: pane.playlistsModel.requestUI("renameFolder", pane.contextEntry.id, []) }
        AppMenuItem { text: "Move to folder…"; onTriggered: pane.playlistsModel.requestUI(pane.contextEntry.kind === "folder" ? "moveFolder" : "move", pane.contextEntry.id, []) }
        AppMenuSeparator {}
        AppMenuItem { text: "Delete"; onTriggered: pane.playlistsModel.requestUI(pane.contextEntry.kind === "folder" ? "deleteFolder" : "delete", pane.contextEntry.id, []) }
    }
}
