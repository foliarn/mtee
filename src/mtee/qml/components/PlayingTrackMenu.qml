import QtQuick
import Mtee

// "…" menu of the fullscreen card. Unlike the list menus it acts on the playing track,
// never on the current selection.
AppMenu {
    id: menu

    required property var workspace
    property string trackId: ""
    property string source: ""
    signal addToPlaylistRequested()

    AppMenuItem {
        objectName: "playingEditInfo"
        text: "Edit info"
        onTriggered: menu.workspace.revealTrackForEdit(menu.trackId, menu.source)
    }
    AppMenuItem {
        objectName: "playingAddToPlaylist"
        text: "Add to playlist…"
        onTriggered: menu.addToPlaylistRequested()
    }
    AppMenuItem {
        objectName: "playingConvert"
        text: "Convert…"
        onTriggered: menu.workspace.addTracksToConvert([menu.trackId])
    }
    AppMenuItem {
        objectName: "playingAnalyze"
        text: "Analyze"
        onTriggered: menu.workspace.analyzeTracks([menu.trackId], false)
    }
    AppMenuItem {
        objectName: "playingReanalyze"
        text: "Re-analyze"
        onTriggered: menu.workspace.analyzeTracks([menu.trackId], true)
    }
    AppMenuItem {
        objectName: "playingShowInExplorer"
        text: "Show in Explorer"
        onTriggered: menu.workspace.showInExplorer(menu.trackId)
    }
}
