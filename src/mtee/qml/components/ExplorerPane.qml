import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// Folder tree: a click on a folder opens it in a tab without unfolding it, the
// chevron or a double click unfolds or folds it, a click on a file selects it and
// a double click plays it. The folder of the active tab is highlighted.
Item {
    id: pane

    required property var workspace

    objectName: "explorerPane"
    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.LeftButton
        onClicked: pane.workspace.clearSelection(pane.workspace.activeGroup)
    }
    readonly property var treeModel: typeof workspace.folderTreeModel === "object"
        ? workspace.folderTreeModel : null
    property string scrollAnchorId: ""
    property string scrollAnchorFallbackId: ""
    property real scrollAnchorViewportY: 0
    property bool clickedAnchorPending: false

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

    function captureTopAnchor() {
        const index = tree.indexAt(1, 1)
        const item = index >= 0 ? tree.itemAtIndex(index) : null
        if (item)
            rememberAnchor(item.modelData, item.y)
    }

    function restoreAnchor() {
        if (!treeModel || typeof treeModel.rowForId !== "function")
            return
        let index = scrollAnchorId ? treeModel.rowForId(scrollAnchorId) : -1
        if (index < 0 && scrollAnchorFallbackId)
            index = treeModel.rowForId(scrollAnchorFallbackId)
        if (index >= 0)
            tree.contentY = index * Theme.treeRowHeight - scrollAnchorViewportY
        scrollAnchorId = ""
        scrollAnchorFallbackId = ""
        clickedAnchorPending = false
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

    function openContextMenu(row, x, y) {
        const data = row.modelData
        if (data.kind === "folder") {
            explorerMenu.folderId = String(data.id)
            explorerMenu.trackIds = []
        } else {
            const selected = workspace.selectedIds
            explorerMenu.folderId = ""
            explorerMenu.trackIds = selected.indexOf(data.id) >= 0 ? selected : [String(data.id)]
        }
        explorerMenu.popup(row, x, y)
    }

    ExplorerContextMenu {
        id: explorerMenu
        objectName: "explorerContextMenu"
        workspace: pane.workspace
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

    ListView {
        id: tree
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        model: pane.treeModel || pane.workspace.explorerRows
        ScrollBar.vertical: ThinScrollBar {}
        MouseArea {
            parent: tree
            x: 0
            y: Math.min(tree.height, Math.max(0, tree.contentHeight - tree.contentY))
            width: tree.width
            height: Math.max(0, tree.height - y)
            z: 10
            acceptedButtons: Qt.LeftButton
            onClicked: pane.workspace.clearSelection(pane.workspace.activeGroup)
        }

        WheelScrollHandler {
            flickable: tree
        }

        delegate: Rectangle {
            id: row

            objectName: "explorerRow"
            required property var modelData
            readonly property bool isFolder: modelData.kind === "folder"
            readonly property bool isLoading: modelData.kind === "loading"
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
                    : row.isLoading ? Theme.textMuted
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
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onPressed: (event) => {
                    if (event.button === Qt.LeftButton)
                        pane.rememberAnchor(row.modelData, row.y)
                }
                onClicked: (event) => {
                    if (row.isLoading)
                        return
                    if (event.button === Qt.RightButton) {
                        pane.openContextMenu(row, event.x, event.y)
                        return
                    }
                    if (row.isFolder) {
                        const onChevron = event.x < chevron.x + chevron.width + 2
                        if (onChevron) {
                            pane.workspace.toggleFolder(row.modelData.id)
                        } else {
                            pane.workspace.openFolder(row.modelData.id)
                        }
                    } else {
                        if (typeof pane.workspace.selectExplorerTrack === "function")
                            pane.workspace.selectExplorerTrack(row.modelData.id, row.modelData.folder)
                        else {
                            pane.workspace.openFolder(row.modelData.folder)
                            pane.workspace.selectTrack(row.modelData.id, "single", [])
                        }
                    }
                }
                onDoubleClicked: {
                    if (row.isLoading)
                        return
                    if (row.isFolder) {
                        if (row.modelData.hasChildren)
                            pane.workspace.toggleFolder(row.modelData.id)
                    } else if (typeof pane.workspace.activateExplorerTrack === "function")
                        pane.workspace.activateExplorerTrack(row.modelData.id, row.modelData.folder)
                    else if (typeof pane.workspace.playTrack === "function")
                        pane.workspace.playTrack(row.modelData.id, row.modelData.folder)
                }
            }
        }
    }
}
