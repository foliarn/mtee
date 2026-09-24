import QtQuick
import QtQuick.Controls.Basic
import Mtee

AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property string trackId: ""
    property string source: ""

    AppMenuItem {
        text: "Play"
        hint: "Enter"
        onTriggered: menu.workspace.playTrack(menu.trackId, menu.source)
    }

    AppMenuItem {
        text: "Edit info"
        hint: "Ctrl+I"
        onTriggered: menu.workspace.showRightPanel("info")
    }

    AddToPlaylistMenu {
        workspace: menu.workspace
        trackIds: menu.trackIds
    }

    AppMenuSeparator {}

    AppMenuItem {
        text: "Convert…"
        onTriggered: {
            menu.workspace.addSelectionToConvert()
            menu.workspace.openConvert()
        }
    }

    AppMenuItem {
        text: "Show in Explorer"
        onTriggered: {
            const track = menu.workspace.track(menu.trackId)
            menu.workspace.setActivity("explorer")
            menu.workspace.openFolder(track.folder)
        }
    }

    AppMenuSeparator {}

    AppMenuItem { text: "Rename…"; hint: "F2"; enabled: false }
    AppMenuItem { text: "Move to trash"; hint: "Del"; enabled: false }
}
