import QtQuick
import QtQuick.Controls.Basic
import Mtee

AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property string trackId: ""
    property string source: ""
    property string folderId: ""

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
        objectName: "analyzeAction"
        text: "Analyze"
        onTriggered: menu.workspace.analyzeTracks(menu.targetIds(), false)
    }

    AppMenuItem {
        objectName: "reanalyzeAction"
        text: "Re-analyze"
        onTriggered: menu.workspace.analyzeTracks(menu.targetIds(), true)
    }

    AppMenuItem {
        text: "Show in Explorer"
        onTriggered: menu.workspace.showInExplorer(menu.trackId)
    }

    AppMenuSeparator {}

    FileActionsMenu {
        workspace: menu.workspace
        trackIds: menu.trackIds
        trackId: menu.trackId
    }

    // The selection when the clicked track is part of it, else the clicked track.
    function targetIds() {
        return trackIds.indexOf(trackId) >= 0 ? trackIds : [trackId]
    }
}
