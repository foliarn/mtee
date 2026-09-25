import QtQuick
import Mtee

AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property string trackId: ""

    title: "File actions"
    enabled: typeof workspace.trashModel !== "undefined"

    AppMenuItem {
        text: "Move to trash…"
        hint: "Del"
        onTriggered: menu.workspace.trashModel.request_recycle(menu.trackIds)
    }
}
