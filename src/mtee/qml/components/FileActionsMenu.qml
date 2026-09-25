import QtQuick
import QtQuick.Controls.Basic
import Mtee

AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property string trackId: ""

    title: "File actions"
    enabled: typeof workspace.fileOperations !== "undefined"

    AppMenuItem {
        text: "Rename…"
        hint: "F2"
        enabled: menu.trackIds.length === 1
        onTriggered: {
            const track = menu.workspace.track(menu.trackId)
            const filename = String(track.filename || "")
            const dot = filename.lastIndexOf(".")
            const stem = dot > 0 ? filename.slice(0, dot) : filename
            menu.workspace.fileOperations.openOperation("rename", stem, menu.trackIds)
        }
    }

    AppMenuItem {
        text: "Move…"
        onTriggered: menu.workspace.fileOperations.openOperation("move", "", menu.trackIds)
    }

    Menu {
        id: moveToMenu
        title: "Move to"
        Instantiator {
            model: menu.workspace.destinationFolders
            delegate: AppMenuItem {
                required property var modelData
                text: modelData.label
                enabled: modelData.available
                onTriggered: menu.workspace.fileOperations.openOperation(
                    "move", modelData.path, menu.trackIds
                )
            }
            onObjectAdded: (index, object) => moveToMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => moveToMenu.removeItem(object)
        }
    }

    AppMenuItem {
        text: "Copy to…"
        onTriggered: menu.workspace.fileOperations.openOperation("copy", "", menu.trackIds)
    }

    Menu {
        id: copyToMenu
        title: "Copy to"
        Instantiator {
            model: menu.workspace.destinationFolders
            delegate: AppMenuItem {
                required property var modelData
                text: modelData.label
                enabled: modelData.available
                onTriggered: menu.workspace.fileOperations.openOperation(
                    "copy", modelData.path, menu.trackIds
                )
            }
            onObjectAdded: (index, object) => copyToMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => copyToMenu.removeItem(object)
        }
    }

    AppMenuSeparator {}

    AppMenuItem {
        text: "Move to trash…"
        hint: "Del"
        onTriggered: menu.workspace.fileOperations.openOperation("trash", "", menu.trackIds)
    }
}
