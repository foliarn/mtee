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

    AppMenuItem {
        text: "Add to playlist…"
        onTriggered: playlistPopup.popup(menu.parent, menu.x, menu.y)
    }
    AddToPlaylistMenu { id: playlistPopup; workspace: menu.workspace; trackIds: menu.targetIds() }

    AppMenuItem {
        visible: menu.source.indexOf("playlist:") === 0 && typeof menu.workspace.playlistModel !== "undefined"
        text: "Remove from playlist"
        onTriggered: menu.workspace.playlistModel.remove(menu.source.split(":")[1], menu.targetIds())
    }
    AppMenuItem {
        visible: menu.source.indexOf("playlist:") === 0
        text: "Move up"
        onTriggered: menu.workspace.movePlaylistEntry(menu.source, menu.trackId, -1)
    }
    AppMenuItem {
        visible: menu.source.indexOf("playlist:") === 0
        text: "Move down"
        onTriggered: menu.workspace.movePlaylistEntry(menu.source, menu.trackId, 1)
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
        onTriggered: menu.workspace.analyzeTracks(typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds(menu.targetIds()) : menu.targetIds(), false)
    }

    AppMenuItem {
        objectName: "reanalyzeAction"
        text: "Re-analyze"
        onTriggered: menu.workspace.analyzeTracks(typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds(menu.targetIds()) : menu.targetIds(), true)
    }

    AppMenuItem {
        text: "Show in Explorer"
        onTriggered: menu.workspace.showInExplorer(typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds([menu.trackId])[0] || "" : menu.trackId)
    }

    AppMenuSeparator {}

    FileActionsMenu {
        workspace: menu.workspace
        trackIds: typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds(menu.trackIds) : menu.trackIds
        trackId: typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds([menu.trackId])[0] || "" : menu.trackId
    }

    // The selection when the clicked track is part of it, else the clicked track.
    function targetIds() {
        return trackIds.indexOf(trackId) >= 0 ? trackIds : [trackId]
    }
}
