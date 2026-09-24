import QtQuick
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

    AppMenuSeparator {}

    AppMenuItem {
        text: "Move to trash…"
        hint: "Del"
        onTriggered: menu.workspace.fileOperations.openOperation("trash", "", menu.trackIds)
    }
}
