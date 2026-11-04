import QtQuick
import Mtee

// Right-click menu of a folder or a source of the explorer tree (plan 132.1 and 132.2), on
// ActionMenu. A source offers Remove from library; a folder offers rename, new folder and delete
// to the Recycle Bin. Actions that need an inline field or a dialog are passed to the pane through
// ``actionRequested``; the tracks of the tree use TrackMenu.
ActionMenu {
    id: menu

    required property var workspace
    property string folderId: ""
    property string rootId: ""
    property bool isRoot: false

    signal actionRequested(string actionId)

    groups: [
        {
            "id": "open",
            "items": [
                { "id": "open", "label": "Open", "objectName": "openFolderAction" },
                { "id": "openRight", "label": "Open to the right", "objectName": "openRightAction" }
            ]
        },
        {
            "id": "analyze",
            "items": [
                { "id": "analyze", "label": "Analyze folder", "hint": "with sub-folders",
                    "objectName": "analyzeAction" },
                { "id": "rescan", "label": "Rescan", "objectName": "rescanAction",
                    "visible": menu.isRoot }
            ]
        },
        {
            "id": "edit",
            "items": [
                { "id": "newFolder", "label": "New folder", "objectName": "newFolderAction" },
                { "id": "rename", "label": "Rename…", "objectName": "renameFolderAction",
                    "visible": !menu.isRoot }
            ]
        },
        {
            "id": "system",
            "items": [
                { "id": "openExplorer", "label": "Open in Windows Explorer",
                    "objectName": "openExplorerAction" }
            ]
        },
        {
            "id": "remove",
            "items": [
                { "id": "removeRoot", "label": "Remove from library…", "danger": true,
                    "objectName": "removeRootAction", "visible": menu.isRoot },
                { "id": "deleteFolder", "label": "Delete folder…", "danger": true,
                    "objectName": "deleteFolderAction", "visible": !menu.isRoot }
            ]
        }
    ]

    onTriggered: (actionId) => {
        if (actionId === "open")
            menu.workspace.openFolder(menu.folderId)
        else if (actionId === "openRight")
            menu.workspace.openFolderAt(menu.folderId, menu.workspace.activeGroup, "right")
        else if (actionId === "analyze")
            menu.workspace.analyzeFolder(menu.folderId, false)
        else if (actionId === "rescan")
            menu.workspace.rescanRoot(menu.rootId)
        else if (actionId === "openExplorer")
            menu.workspace.openFolderInExplorer(menu.folderId)
        else if (actionId === "deleteFolder")
            menu.workspace.recycleFolder(menu.folderId)
        else
            menu.actionRequested(actionId)
    }
}
