import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The Playlists tool window (plan 132.4): playlists and playlist folders as NavItem rows of a
// regular NavList. Liked tracks comes first, with its default heart cover. Menus are ActionMenus
// (P7). Tracks dragged from a list land on the playlist row under the pointer; playlists and
// folders are dragged by their rows (a folder drop moves the node into it, a playlist drop puts
// it before that playlist). A folder delete asks what to do with its contents (U13).
Item {
    id: pane
    required property var workspace
    readonly property bool live: typeof workspace.playlistModel !== "undefined"
    readonly property var playlistsModel: live ? workspace.playlistModel : null
    readonly property string activePlaylist: workspace.groups.length ? workspace.activeTabId.split(":")[1] || "" : ""
    property var contextEntry: ({})
    // The row a drag is over (a playlist for tracks, a folder or playlist for a node), by id.
    property string dropId: ""
    // The playlist or folder being renamed inline, by id.
    property string renamingId: ""
    // A playlist or folder row being dragged: its id and kind, and the row under the pointer
    // (undefined until the pointer moves, null over empty space, which means the root).
    property string nodeDragId: ""
    property bool nodeDragIsFolder: false
    property var nodeTargetRow: undefined
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
        AppMenuItem { objectName: "newFolderMenuItem"; text: "New folder"; visible: pane.live; onTriggered: pane.playlistsModel.createUntitledFolder("") }
        AppMenuItem { objectName: "resumeImportMenuItem"; text: "Resume interrupted import…"; visible: pane.live && pane.playlistsModel.pendingImports.length > 0; height: visible ? 28 : 0; implicitHeight: visible ? 28 : 0; onTriggered: pane.playlistsModel.requestUI("resume", "", []) }
        AppMenuItem { objectName: "importPlaylistMenuItem"; text: "Import playlist…"; visible: pane.live; onTriggered: pane.playlistsModel.requestUI("import", "", []) }
    }

    // What a row shows beyond the shared NavItem values (see NavList.decorate). A folder has a
    // folder tile; Liked tracks has its heart (or its own cover); a playlist has its cover, else
    // the mosaic of its tracks' covers, else a note.
    function rowState(data) {
        const folder = data.kind === "folder"
        const id = String(data.id || "")
        const liked = id === "liked"
        const cover = String(data.coverUrl || "")
        const covers = folder || liked ? [] : (data.covers || [])
        let leading = "music"
        if (folder)
            leading = "folder"
        else if (cover.length > 0)
            leading = cover
        else if (liked)
            leading = "heart"
        else if (covers.length > 0)
            leading = ""
        return {
            "leading": leading,
            "covers": covers,
            "tileGradient": liked && cover.length === 0,
            "subtitle": folder ? "" : String(data.summary || ""),
            "expandable": folder,
            "expanded": data.expanded === true,
            "trailing": !folder && data.pinned === true ? "Pinned" : "",
            "dropTarget": id.length > 0 && id === pane.dropId,
            "renaming": folder && id.length > 0 && id === pane.renamingId
        }
    }

    function rowAtPoint(x, y) {
        const index = tree.indexAt(x + tree.contentX, y + tree.contentY)
        return index >= 0 ? tree.rowAt(index) : null
    }

    function rowById(rowId) {
        const index = tree.indexOfId(rowId)
        return index >= 0 ? tree.rowAt(index) : null
    }

    function openRow(rowId) {
        const row = rowById(rowId)
        if (row && row.kind === "folder")
            toggleRow(rowId)
        else
            pane.workspace.openPlaylist(rowId)
    }

    function toggleRow(rowId) {
        if (pane.live)
            pane.playlistsModel.toggleFolder(rowId)
    }

    function showMenu(rowId, x, y) {
        const entry = pane.live ? rowById(rowId) : null
        if (!entry)
            return
        pane.contextEntry = entry
        context.groups = pane.menuGroups(entry)
        context.popup(tree, x, y)
    }

    // The entries of the menu of a row (P7). Only the entries whose backend exists are listed.
    function menuGroups(entry) {
        const id = String(entry.id || "")
        if (entry.kind === "folder") {
            return [
                { "id": "create", "items": [
                    { "id": "newPlaylist", "label": "New playlist here", "objectName": "folderNewPlaylistAction" },
                    { "id": "newFolder", "label": "New folder here", "objectName": "folderNewFolderAction" }
                ] },
                { "id": "rename", "items": [
                    { "id": "rename", "label": "Rename", "objectName": "folderRenameAction" }
                ] },
                { "id": "delete", "items": [
                    { "id": "deleteFolder", "label": "Delete…", "danger": true, "objectName": "folderDeleteAction" }
                ] }
            ]
        }
        const play = { "id": "play", "items": [
            { "id": "play", "label": "Play", "objectName": "playlistPlayAction" },
            { "id": "enqueue", "label": "Add to queue", "objectName": "enqueuePlaylistAction" }
        ] }
        if (id === "liked")
            return [play, { "id": "cover", "items": [
                { "id": "cover", "label": "Change cover…", "objectName": "likedCoverAction" }
            ] }]
        const folders = pane.playlistsModel ? pane.playlistsModel.folders : []
        const moveTo = [{ "id": "move:", "label": "Playlists (root)" }]
            .concat(folders.map(folder => ({ "id": "move:" + folder.id, "label": folder.name })))
        return [
            play,
            { "id": "edit", "items": [
                { "id": "edit", "label": "Edit details…", "objectName": "playlistEditAction" },
                { "id": "cover", "label": "Change cover…", "objectName": "playlistCoverAction" },
                { "id": "duplicate", "label": "Duplicate", "objectName": "playlistDuplicateAction" },
                { "id": "pin", "label": entry.pinned === true ? "Unpin" : "Pin", "objectName": "playlistPinAction" },
                { "id": "moveTo", "label": "Move to folder", "submenu": moveTo, "objectName": "playlistMoveAction" }
            ] },
            { "id": "export", "items": [
                { "id": "export", "label": "Export…", "objectName": "playlistExportAction" }
            ] },
            { "id": "delete", "items": [
                { "id": "delete", "label": "Delete…", "danger": true, "objectName": "playlistDeleteAction" }
            ] }
        ]
    }

    function runMenuAction(actionId) {
        const entry = pane.contextEntry
        const id = String(entry.id || "")
        const model = pane.playlistsModel
        if (!model)
            return
        if (actionId.indexOf("move:") === 0) {
            model.move(id, actionId.substring(5), entry.kind === "folder", "")
            return
        }
        switch (actionId) {
        case "play": pane.workspace.playPlaylist(id, false); break
        case "enqueue": pane.workspace.enqueuePlaylist(id); break
        case "edit": case "cover": case "export": case "delete": model.requestUI(actionId, id, []); break
        case "duplicate": model.duplicate(id); break
        case "pin": model.pin(id, entry.pinned !== true); break
        case "newPlaylist": model.createUntitled(id, []); break
        case "newFolder": model.createUntitledFolder(id); break
        case "rename": pane.renamingId = id; break
        case "deleteFolder": pane.askDeleteFolder(entry); break
        }
    }

    // An empty folder goes at once; otherwise the user chooses what happens to its contents (U13).
    function askDeleteFolder(entry) {
        const id = String(entry.id)
        const info = pane.playlistsModel.folderSummary(id)
        if (info.empty) {
            pane.playlistsModel.deleteFolder(id, false)
            return
        }
        folderDelete.folderId = id
        folderDelete.folderName = String(entry.name || "")
        folderDelete.folderInfo = info
        folderDelete.open()
    }

    // The tracks of a list land on the playlist row under the pointer, not on a folder or Liked.
    function updateTrackDrop(drag) {
        const row = pane.rowAtPoint(drag.x, drag.y)
        const accepts = !!row && row.kind !== "folder" && row.id !== "liked"
            && !!drag.source && drag.source.dragCanAdd === true
        pane.dropId = accepts ? String(row.id) : ""
    }

    // A node dropped on a row: a folder takes it inside, a playlist puts it before that playlist
    // in the same folder, empty space moves it to the root. A row that is not a target does nothing.
    function moveNode(identity, isFolder, target) {
        if (target === null) {
            pane.playlistsModel.move(identity, "", isFolder, "")
        } else if (target.id !== identity && target.id !== "liked") {
            if (target.kind === "folder")
                pane.playlistsModel.move(identity, String(target.id), isFolder, "")
            else
                pane.playlistsModel.move(identity, String(target.folder || ""), isFolder, String(target.id))
        }
    }

    function nodeTargetId(target) {
        if (!target || target.id === pane.nodeDragId || target.id === "liked")
            return ""
        return String(target.id)
    }

    NavList {
        id: tree
        objectName: "playlistsTree"
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        size: "regular"
        // The playlist that is open is the accent row; a click opens or folds a row.
        selectionEnabled: false
        rowObjectName: ""
        accentIds: pane.activePlaylist.length > 0 ? [pane.activePlaylist] : []
        model: pane.live ? pane.playlistsModel.tree : pane.workspace.playlists
        decorate: pane.rowState
        // The sections of the plugins that chose Playlists, below the local tree.
        footer: PluginSections { workspace: pane.workspace; activity: "playlists"; width: tree.width; rowSize: "regular" }
        ScrollBar.vertical: ThinScrollBar {}

        onRowClicked: (rowId, modifiers) => pane.openRow(rowId)
        onRowChevronClicked: rowId => pane.toggleRow(rowId)
        onRowContextRequested: (rowId, x, y) => pane.showMenu(rowId, x, y)
        onRowRenamed: (rowId, text) => {
            pane.renamingId = ""
            if (pane.live)
                pane.playlistsModel.renameFolder(rowId, text)
        }
        onRowRenameCancelled: rowId => { pane.renamingId = "" }
        onRowDragBegun: rowId => {
            const row = pane.live ? pane.rowById(rowId) : null
            pane.nodeDragId = row && rowId !== "liked" ? rowId : ""
            pane.nodeDragIsFolder = !!row && row.kind === "folder"
            pane.nodeTargetRow = undefined
        }
        onRowDragMoved: (rowId, x, y) => {
            if (pane.nodeDragId.length === 0)
                return
            const target = pane.rowAtPoint(x, y)
            pane.nodeTargetRow = target
            pane.dropId = pane.nodeTargetId(target)
        }
        onRowDragEnded: rowId => {
            const identity = pane.nodeDragId
            const target = pane.nodeTargetRow
            pane.nodeDragId = ""
            pane.nodeTargetRow = undefined
            pane.dropId = ""
            if (identity.length > 0 && target !== undefined && pane.live)
                pane.moveNode(identity, pane.nodeDragIsFolder, target)
        }
    }

    // Tracks dragged from a list land on the playlist row under the pointer.
    DropArea {
        id: trackDrop
        objectName: "playlistsTrackDrop"
        anchors.fill: tree
        keys: ["mtee-tracks"]
        enabled: pane.live
        onEntered: drag => pane.updateTrackDrop(drag)
        onPositionChanged: drag => pane.updateTrackDrop(drag)
        onExited: pane.dropId = ""
        onDropped: drop => {
            const target = pane.dropId
            pane.dropId = ""
            if (target.length > 0 && drop.source && drop.source.dragCanAdd === true)
                pane.playlistsModel.add(target, drop.source.dragTrackIds)
        }
    }

    // A folder created at once with its default name starts in inline rename (like Explorer).
    Connections {
        target: pane.playlistsModel
        ignoreUnknownSignals: true
        function onFolderCreated(identity) { pane.renamingId = identity }
    }

    ActionMenu {
        id: context
        objectName: "playlistsContextMenu"
        onTriggered: actionId => pane.runMenuAction(actionId)
    }

    ConfirmDialog {
        id: folderDelete
        objectName: "folderDeleteDialog"
        property string folderId: ""
        property string folderName: ""
        property var folderInfo: ({})
        title: "Delete folder \"" + folderName + "\"?"
        text: "It holds " + folderInfo.folders + " subfolders and " + folderInfo.playlists
            + " playlists. Keep them: they move up one level and keep their order. "
            + "Or delete everything inside, " + folderInfo.allPlaylists + " playlists in all."
        buttons: [
            { "key": "keep", "label": "Delete folder, keep playlists", "kind": "primary" },
            { "key": "all", "label": "Delete everything", "kind": "danger" },
            { "key": "cancel", "label": "Cancel", "kind": "ghost" }
        ]
        onAnswered: key => {
            if (key === "keep" || key === "all")
                pane.playlistsModel.deleteFolder(folderDelete.folderId, key === "keep")
        }
    }
}
