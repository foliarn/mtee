import QtQuick
import QtQuick.Controls.Basic
import Mtee

// "+" menu: a check marks a playlist that already holds every given track.
AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []

    title: "Add to playlist"

    function holdsAll(playlistId) {
        if (trackIds.length === 0)
            return false
        for (const trackId of trackIds) {
            if (workspace.playlistsContaining(trackId, workspace.revision).indexOf(playlistId) < 0)
                return false
        }
        return true
    }

    Instantiator {
        model: menu.workspace.playlists
        delegate: AppMenuItem {
            required property var modelData
            text: modelData.name
            mark: menu.holdsAll(modelData.id)
            onTriggered: menu.workspace.togglePlaylist(menu.trackIds, modelData.id)
        }
        onObjectAdded: (index, object) => menu.insertItem(index, object)
        onObjectRemoved: (index, object) => menu.removeItem(object)
    }

    AppMenuSeparator {}

    AppMenuItem {
        text: "New playlist"
        onTriggered: menu.workspace.addToNewPlaylist(menu.trackIds)
    }
}
