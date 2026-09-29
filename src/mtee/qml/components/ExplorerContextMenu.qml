import QtQuick
import Mtee

// Right-click menu of the explorer tree: a folder (with everything inside it) or
// the tracks under the pointer.
AppMenu {
    id: menu

    required property var workspace
    property string folderId: ""
    property var trackIds: []
    readonly property bool forFolder: folderId.length > 0

    AppMenuItem {
        objectName: "analyzeAction"
        text: menu.forFolder ? "Analyze folder" : "Analyze"
        hint: menu.forFolder ? "with sub-folders" : ""
        onTriggered: menu.run(false)
    }

    AppMenuItem {
        objectName: "reanalyzeAction"
        text: menu.forFolder ? "Re-analyze folder" : "Re-analyze"
        hint: menu.forFolder ? "with sub-folders" : ""
        onTriggered: menu.run(true)
    }

    function run(force) {
        if (forFolder)
            workspace.analyzeFolder(folderId, force)
        else
            workspace.analyzeTracks(trackIds, force)
    }
}
