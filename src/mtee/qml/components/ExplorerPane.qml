import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// Folder tree on NavList (plan 132.3): a click on a folder opens it in a tab without unfolding it,
// the chevron or a double click unfolds or folds it, a click on a song opens its folder and
// selects it, and a double click plays it. Ctrl and Shift clicks select songs across folders
// (U14): that selection is the workspace selection with source "explorer", so Del, the track
// menu and the drag to a folder act on all of it. Dragging a folder row starts the "folder"
// payload of the center drop zones; dropping a folder on another tree folder does nothing.
Item {
    id: pane

    required property var workspace

    objectName: "explorerPane"
    readonly property var treeModel: typeof workspace.folderTreeModel === "object"
        ? workspace.folderTreeModel : null
    property string scrollAnchorId: ""
    property string scrollAnchorFallbackId: ""
    property real scrollAnchorViewportY: 0
    property bool clickedAnchorPending: false
    readonly property bool canMoveFiles: typeof workspace.moveTracksToFolder === "function"
    // The pointer of the drag in pane coordinates, shared by the track and the folder drag.
    property real pointerX: 0
    property real pointerY: 0
    property bool trackDragActive: false
    property string dragTitle: ""
    property string dragArtist: ""
    property int dragCount: 0
    // The folder row under the pointer while songs are dragged onto the tree ("" for none).
    property string dropTargetId: ""
    // "rename": what the inline field of the tree row does on commit.
    property string editMode: ""

    // A root is listed as "root:<id>" in the tree but a track in its top level
    // reports "folder:<id>/", so both spellings must compare equal.
    function folderKey(identity) {
        const text = String(identity || "")
        return text.startsWith("folder:") && text.endsWith("/") ? "root:" + text.slice(7, -1) : text
    }

    function indexOfRow(identity) {
        if (pane.treeModel && typeof pane.treeModel.rowForId === "function")
            return pane.treeModel.rowForId(identity)
        return tree.indexOfId(identity)
    }

    // The data of a visible row, or null when the row is not on screen.
    function rowDataFor(identity) {
        const index = indexOfRow(identity)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        return item ? item.rowData : null
    }

    function statusFor(data) {
        const availability = String(data.availability || "")
        if (availability === "" || availability === "available")
            return { "text": "", "tone": "muted" }
        if (availability === "scanning")
            return { "text": "Scanning…", "tone": "muted" }
        if (availability === "unavailable")
            return { "text": "Unavailable", "tone": "danger" }
        return { "text": "Partial", "tone": "muted" }
    }

    // What the tree row shows beyond the shared NavItem values (see NavList.decorate).
    function treeRowState(data) {
        const folder = data.kind === "folder"
        const loading = data.kind === "loading"
        const identity = String(data.id || "")
        const status = folder ? statusFor(data) : { "text": "", "tone": "muted" }
        return {
            "expandable": folder && data.hasChildren === true,
            "muted": loading,
            "accent": !loading && (pane.workspace.activeFolder === identity
                || pane.workspace.playingId === identity),
            "trailing": status.text,
            "trailingTone": status.tone,
            "dropTarget": folder && pane.dropTargetId === identity
        }
    }

    // A root is listed as "root:<id>" in the tree; a folder id names a folder of a root.
    function parentFolderId(rowData) {
        if (rowData.kind !== "folder")
            return String(rowData.folder || "")
        const id = String(rowData.id || "")
        if (id.startsWith("root:"))
            return ""
        if (!id.startsWith("folder:"))
            return ""
        const ref = id.substring(7)
        const rootSeparator = ref.indexOf("/")
        const parentSeparator = ref.lastIndexOf("/")
        if (rootSeparator < 0)
            return ""
        if (parentSeparator <= rootSeparator)
            return "root:" + ref.substring(0, rootSeparator)
        return "folder:" + ref.substring(0, parentSeparator)
    }

    function rememberAnchor(rowData, rowY) {
        scrollAnchorId = String(rowData.id || "")
        scrollAnchorFallbackId = parentFolderId(rowData)
        scrollAnchorViewportY = rowY - tree.contentY
        clickedAnchorPending = true
        Qt.callLater(() => clickedAnchorPending = false)
    }

    function rememberRow(identity) {
        const index = indexOfRow(identity)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        if (item)
            rememberAnchor(item.rowData, item.y)
    }

    function captureTopAnchor() {
        const index = tree.indexAt(1 + tree.contentX, 1 + tree.contentY)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        if (item)
            rememberAnchor(item.rowData, item.y)
    }

    function restoreAnchor() {
        if (!treeModel || typeof treeModel.rowForId !== "function")
            return
        let index = scrollAnchorId ? treeModel.rowForId(scrollAnchorId) : -1
        if (index < 0 && scrollAnchorFallbackId)
            index = treeModel.rowForId(scrollAnchorFallbackId)
        if (index >= 0)
            tree.contentY = index * tree.rowHeight - scrollAnchorViewportY
        scrollAnchorId = ""
        scrollAnchorFallbackId = ""
        clickedAnchorPending = false
    }

    // ----------------------------------------------------------- drags

    function setPointer(x, y) {
        const point = tree.mapToItem(pane, x, y)
        pane.pointerX = point.x
        pane.pointerY = point.y
    }

    // A song drag: the selection moves together; a multi-folder selection has no source folder.
    function beginTrackDrag(rowId) {
        const data = rowDataFor(rowId)
        if (!data)
            return
        if (workspace.selectedIds.indexOf(rowId) < 0)
            pane.pickTrack(rowId)
        const ids = Array.from(workspace.selectedIds)
        const info = typeof workspace.track === "function" ? workspace.track(rowId) : ({})
        dragSession.dragTrackIds = ids
        dragSession.dragEntryIds = []
        dragSession.dragCanAdd = true
        dragSession.dragSource = ids.length === 1 ? String(data.folder || "") : ""
        pane.dragCount = ids.length
        pane.dragTitle = info.title || String(data.name || data.title || "")
        pane.dragArtist = info.artist || ""
        pane.trackDragActive = true
    }

    // A folder dragged to a center window's edge (plan 131.7): payload {type: "folder", folderId}.
    property bool folderDragActive: false
    property string folderDragName: ""

    function beginFolderDrag(rowId) {
        const data = rowDataFor(rowId)
        if (!data)
            return
        folderSession.payload = ({ "type": "folder", "folderId": rowId })
        pane.folderDragName = String(data.name || "")
        pane.folderDragActive = true
    }

    function endDrags() {
        pane.trackDragActive = false
        pane.folderDragActive = false
        pane.dropTargetId = ""
    }

    function finishDrags() {
        if (pane.trackDragActive)
            dragSession.Drag.drop()
        if (pane.folderDragActive)
            folderSession.Drag.drop()
        pane.endDrags()
    }

    function cancelDrags() {
        if (pane.trackDragActive)
            dragSession.Drag.cancel()
        if (pane.folderDragActive)
            folderSession.Drag.cancel()
        pane.endDrags()
    }

    // The folder row under a song drag; a folder the songs come from is not a target.
    function updateTreeDropTarget(drag) {
        const index = tree.indexAt(drag.x + tree.contentX, drag.y + tree.contentY)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        const identity = item ? String(item.rowData.id || "") : ""
        const isFolder = !!item && item.rowData.kind === "folder"
        const same = !!drag.source && folderKey(drag.source.dragSource) === folderKey(identity)
        pane.dropTargetId = isFolder && !same ? identity : ""
    }

    Component.onDestruction: cancelDrags()

    Shortcut {
        sequence: "Escape"
        enabled: pane.trackDragActive || pane.folderDragActive
        onActivated: pane.cancelDrags()
    }

    Connections {
        target: pane.Window.window
        function onActiveChanged() {
            if (!pane.Window.window.active)
                pane.cancelDrags()
        }
    }

    Timer {
        interval: 35
        repeat: true
        running: pane.trackDragActive || pane.folderDragActive
        onTriggered: {
            const point = pane.mapToItem(tree, pane.pointerX, pane.pointerY)
            if (point.y < 28 && point.y >= -12)
                tree.contentY = Math.max(0, tree.contentY - 12)
            else if (point.y > tree.height - 28 && point.y <= tree.height + 12)
                tree.contentY = Math.min(Math.max(0, tree.contentHeight - tree.height), tree.contentY + 12)
        }
    }

    TrackDragPreview {
        objectName: "explorerDragPreview"
        parent: Overlay.overlay
        visible: pane.trackDragActive
        trackTitle: pane.dragTitle
        artist: pane.dragArtist
        count: pane.dragCount
        readonly property var pointer: pane.mapToItem(parent, pane.pointerX, pane.pointerY)
        x: Math.max(8, Math.min(parent.width - width - 8, pointer.x + 16))
        y: Math.max(8, Math.min(parent.height - height - 8, pointer.y + 16))
    }

    Item {
        id: dragSession
        parent: Overlay.overlay
        width: 1; height: 1
        readonly property var pointer: pane.mapToItem(parent, pane.pointerX, pane.pointerY)
        x: pointer.x; y: pointer.y
        property var dragTrackIds: []
        property var dragEntryIds: []
        property string dragSource: ""
        property bool dragCanAdd: false
        Drag.active: pane.trackDragActive
        Drag.source: dragSession
        Drag.keys: ["mtee-tracks"]
        Drag.supportedActions: Qt.MoveAction | Qt.CopyAction
    }

    // The folder drag source: only the drop zones of the center windows take it ("mtee-folder").
    Item {
        id: folderSession
        parent: Overlay.overlay
        width: 1; height: 1
        readonly property var pointer: pane.mapToItem(parent, pane.pointerX, pane.pointerY)
        x: pointer.x; y: pointer.y
        property var payload: ({})
        Drag.active: pane.folderDragActive
        Drag.source: folderSession
        Drag.keys: ["mtee-folder"]
        Drag.supportedActions: Qt.CopyAction
    }

    Rectangle {
        objectName: "explorerFolderDragPreview"
        parent: Overlay.overlay
        visible: pane.folderDragActive
        width: folderDragLabel.implicitWidth + 24
        height: 30
        radius: Theme.radiusControl
        color: Theme.surface
        border.width: 1
        border.color: Theme.primary
        z: 1000
        enabled: false
        readonly property var pointer: pane.mapToItem(parent, pane.pointerX, pane.pointerY)
        x: Math.max(8, Math.min(parent.width - width - 8, pointer.x + 16))
        y: Math.max(8, Math.min(parent.height - height - 8, pointer.y + 16))

        Text {
            id: folderDragLabel
            anchors.centerIn: parent
            text: pane.folderDragName
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }

    // ----------------------------------------------------------- selection of songs

    // Plain click on a song: it is selected alone and its folder is opened (as before 132.3).
    function pickTrack(identity) {
        if (typeof workspace.pickExplorerTrack === "function")
            workspace.pickExplorerTrack(identity)
        else
            workspace.selectTrack(identity, "single", [])
    }

    // Ctrl or Shift click on a song: the selection spans folders, no folder is opened.
    function extendTrack(identity, shift) {
        if (typeof workspace.extendExplorerSelection === "function") {
            workspace.extendExplorerSelection(identity, shift)
            return
        }
        const order = (workspace.explorerRows || [])
            .filter(row => row.kind !== "folder" && row.kind !== "loading")
            .map(row => String(row.id))
        workspace.selectTrack(identity, shift ? "range" : "toggle", order)
    }

    // ----------------------------------------------------------- folder actions

    function handleFolderAction(actionId) {
        const folder = explorerMenu.folderId
        if (actionId === "newFolder") {
            // A new folder is made at once as "Unnamed folder NN"; rename is a separate action.
            pane.workspace.createUnnamedFolder(folder)
        } else if (actionId === "rename") {
            beginFolderEdit(folder, "rename")
        } else if (actionId === "removeRoot") {
            const data = rowDataFor(folder)
            removeRootDialog.rootId = explorerMenu.rootId
            removeRootDialog.rootName = data ? String(data.name) : ""
            removeRootDialog.open()
        }
    }

    // Starts the inline field of a folder row for a new folder or a rename (plan 132.2).
    function beginFolderEdit(identity, mode) {
        const index = indexOfRow(identity)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        if (!item)
            return
        pane.editMode = mode
        item.renameSeed = mode === "rename" ? String(item.rowData.name || "") : ""
        item.renaming = true
    }

    // A folder made as "Unnamed folder NN" starts in inline rename as soon as its row exists (the
    // tree reloads the parent first, so the row is waited for a moment).
    property string pendingRenameId: ""
    property int pendingRenameTries: 0
    Timer {
        id: renameTimer
        interval: 80
        repeat: true
        onTriggered: {
            const identity = pane.pendingRenameId
            pane.pendingRenameTries += 1
            if (identity.length === 0 || pane.pendingRenameTries > 40) {
                renameTimer.stop()
                pane.pendingRenameId = ""
                return
            }
            if (pane.rowDataFor(identity)) {
                renameTimer.stop()
                pane.pendingRenameId = ""
                pane.beginFolderEdit(identity, "rename")
            }
        }
    }
    Connections {
        target: pane.workspace
        ignoreUnknownSignals: true
        function onFolderRenameRequested(identity) {
            pane.pendingRenameId = identity
            pane.pendingRenameTries = 0
            renameTimer.restart()
        }
    }

    function finishFolderEdit(identity, mode, text) {
        if (mode === "rename")
            pane.workspace.renameFolder(identity, text)
    }

    function openContextMenu(identity, x, y) {
        const data = rowDataFor(identity)
        if (!data || data.kind === "loading")
            return
        if (data.kind === "folder") {
            explorerMenu.folderId = identity
            explorerMenu.isRoot = identity.indexOf("root:") === 0
            explorerMenu.rootId = explorerMenu.isRoot ? identity.substring(5) : ""
            explorerMenu.popup(tree, x, y)
            return
        }
        if (workspace.selectedIds.indexOf(identity) < 0)
            pane.pickTrack(identity)
        const ids = Array.from(workspace.selectedIds)
        trackMenu.trackId = identity
        trackMenu.trackIds = ids
        trackMenu.orderedIds = ids
        trackMenu.captureQueueTargets()
        trackMenu.prepare(data.available !== false)
        trackMenu.popup(tree, x, y)
    }

    ExplorerContextMenu {
        id: explorerMenu
        objectName: "explorerContextMenu"
        workspace: pane.workspace
        onActionRequested: (actionId) => pane.handleFolderAction(actionId)
    }

    // Removing a source keeps its files and its analysis, edits and stats (U12).
    ConfirmDialog {
        id: removeRootDialog
        objectName: "removeRootDialog"
        property string rootId: ""
        property string rootName: ""
        title: rootName.length > 0 ? "Remove “" + rootName + "” from the library?"
            : "Remove this source from the library?"
        text: "Your files stay on disk. Analysis and edits are kept if you add the folder again."
        buttons: [
            { "key": "cancel", "label": "Cancel", "kind": "ghost" },
            { "key": "remove", "label": "Remove", "kind": "danger" }
        ]
        onAnswered: (key) => {
            if (key === "remove" && rootId.length > 0)
                pane.workspace.removeRoot(rootId)
        }
    }

    // The tracks of the tree have the same menu as the tracks of a list.
    TrackMenu {
        id: trackMenu
        objectName: "explorerTrackMenu"
        workspace: pane.workspace
        listKind: "explorer"
        source: "explorer"
    }

    FolderDialog {
        id: folderPicker
        title: "Add a music folder"
        onAccepted: pane.workspace.addRoot(selectedFolder.toString())
    }

    Connections {
        target: pane.treeModel
        function onRowsAboutToChange() {
            if (!pane.clickedAnchorPending)
                pane.captureTopAnchor()
        }
        function onRowsChanged() {
            Qt.callLater(pane.restoreAnchor)
        }
    }

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

    NavList {
        id: tree
        objectName: "explorerTree"
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        size: "compact"
        // The Explorer decides what a click selects (pickTrack and extendTrack).
        selectionEnabled: false
        rowObjectName: "explorerRow"
        selectedIds: pane.workspace.selectedIds
        model: pane.treeModel || pane.workspace.explorerRows
        decorate: pane.treeRowState
        // The sections of the plugins that chose the Explorer: none without a plugin.
        footer: PluginSections { workspace: pane.workspace; activity: "explorer"; width: tree.width }
        ScrollBar.vertical: ThinScrollBar {}

        onRowClicked: (rowId, modifiers) => {
            const data = pane.rowDataFor(rowId)
            if (!data || data.kind === "loading")
                return
            if (data.kind === "folder") {
                if (modifiers & (Qt.ControlModifier | Qt.ShiftModifier))
                    return
                pane.rememberRow(rowId)
                pane.workspace.openFolder(rowId)
                return
            }
            if (modifiers & (Qt.ControlModifier | Qt.ShiftModifier)) {
                pane.extendTrack(rowId, (modifiers & Qt.ShiftModifier) !== 0)
            } else if (typeof pane.workspace.selectExplorerTrack === "function") {
                pane.workspace.selectExplorerTrack(rowId, data.folder)
            } else {
                pane.workspace.openFolder(data.folder)
                pane.workspace.selectTrack(rowId, "single", [])
            }
        }
        onRowDoubleClicked: (rowId) => {
            const data = pane.rowDataFor(rowId)
            if (!data || data.kind === "loading")
                return
            if (data.kind === "folder") {
                if (data.hasChildren)
                    pane.workspace.toggleFolder(rowId)
            } else if (typeof pane.workspace.activateExplorerTrack === "function")
                pane.workspace.activateExplorerTrack(rowId, data.folder)
            else if (typeof pane.workspace.playTrack === "function")
                pane.workspace.playTrack(rowId, data.folder)
        }
        onRowChevronClicked: (rowId) => {
            pane.rememberRow(rowId)
            pane.workspace.toggleFolder(rowId)
        }
        onRowContextRequested: (rowId, x, y) => pane.openContextMenu(rowId, x, y)
        onRowRenamed: (rowId, text) => pane.finishFolderEdit(rowId, pane.editMode, text)
        onRowDragBegun: (rowId) => {
            const data = pane.rowDataFor(rowId)
            if (!data)
                return
            if (data.kind === "folder")
                pane.beginFolderDrag(rowId)
            else
                pane.beginTrackDrag(rowId)
        }
        onRowDragMoved: (rowId, x, y) => pane.setPointer(x, y)
        onRowDragEnded: (rowId) => pane.finishDrags()
    }

    // Songs dragged over the tree land on the folder row under the pointer (file move).
    DropArea {
        id: treeDrop
        objectName: "explorerTreeDrop"
        anchors.fill: tree
        keys: ["mtee-tracks"]
        enabled: pane.canMoveFiles
        onEntered: drag => pane.updateTreeDropTarget(drag)
        onPositionChanged: drag => pane.updateTreeDropTarget(drag)
        onExited: pane.dropTargetId = ""
        onDropped: drop => {
            const target = pane.dropTargetId
            pane.dropTargetId = ""
            if (target.length > 0 && drop.source)
                pane.workspace.moveTracksToFolder(drop.source.dragTrackIds, target)
        }
    }
}
