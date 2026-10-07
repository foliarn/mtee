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
        onTriggered: menu.run()
    }

    function run() {
        if (forFolder)
            workspace.analyzeFolder(folderId, false)
        else
            workspace.analyzeTracks(trackIds, false)
    }
}
