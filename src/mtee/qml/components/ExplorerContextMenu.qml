import QtQuick
import Mtee

// Right-click menu of a folder of the explorer tree (with everything inside it). The tracks of
// the tree use TrackMenu.
AppMenu {
    id: menu

    required property var workspace
    property string folderId: ""

    AppMenuItem {
        objectName: "analyzeAction"
        text: "Analyze folder"
        hint: "with sub-folders"
        onTriggered: menu.workspace.analyzeFolder(menu.folderId, false)
    }
}
