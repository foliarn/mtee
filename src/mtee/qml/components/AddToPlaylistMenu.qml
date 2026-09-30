import QtQuick
import QtQuick.Controls.Basic
import Mtee

Popup {
    id: menu
    required property var workspace
    property var trackIds: []
    property var localIds: []
    readonly property var choices: {
        workspace.revision
        return Array.from(workspace.playlists).filter(p => p.name.toLowerCase().indexOf(search.text.toLowerCase()) >= 0).sort((a, b) => {
            const savedA = menu.holdsAll(a.id), savedB = menu.holdsAll(b.id)
            return savedA === savedB ? String(b.updated_at_utc || "").localeCompare(String(a.updated_at_utc || "")) : savedA ? -1 : 1
        })
    }
    width: Math.min(350, parent ? parent.width - 16 : 350)
    height: Math.min(520, Math.max(245, choices.length * 68 + 250))
    padding: 16
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Connections {
        target: typeof menu.workspace.playlistModel !== "undefined" ? menu.workspace.playlistModel : null
        function onPlaylistCreated() { menu.close() }
    }
    background: Rectangle { color: Theme.surface; radius: 8; border.color: Theme.separator }
    function popup(anchor, offsetX, offsetY) {
        localIds = typeof workspace.localTrackIds === "function" ? workspace.localTrackIds(trackIds) : trackIds
        const overlay = Overlay.overlay
        parent = overlay
        const point = anchor.mapToItem(overlay, offsetX, offsetY)
        x = Math.max(8, Math.min(point.x, overlay.width - width - 8))
        y = Math.max(8, Math.min(point.y, overlay.height - height - 8))
        open()
    }
    function holdsAll(playlistId) {
        if (!localIds.length) return false
        for (const trackId of localIds)
            if (workspace.playlistsContaining(trackId, workspace.revision).indexOf(playlistId) < 0) return false
        return true
    }
    contentItem: Item {
        Text { id: title; text: "Add to playlist"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.DemiBold }
        TextField {
            id: search
            objectName: "playlistMenuSearch"
            anchors.top: title.bottom; anchors.topMargin: 14
            width: parent.width; height: 38
            placeholderText: "Search playlists"
            color: Theme.textPrimary; placeholderTextColor: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: 16
            background: Rectangle { color: Theme.chrome; radius: 5; border.color: search.activeFocus ? Theme.focus : Theme.separator }
        }
        TextButton { id: create; anchors.top: search.bottom; anchors.topMargin: 8; text: "+ New playlist"; kind: "ghost"; onClicked: menu.workspace.addToNewPlaylist(menu.trackIds) }
        ListView {
            anchors.top: create.bottom; anchors.topMargin: 12
            anchors.bottom: close.top; anchors.bottomMargin: 8
            width: parent.width
            clip: true
            model: menu.choices
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}
            delegate: Item {
                id: entry
                required property var modelData
                required property int index
                width: ListView.view.width
                height: 68 + (index === 0 || menu.holdsAll(modelData.id) !== menu.holdsAll(menu.choices[index - 1].id) ? 30 : 0)
                readonly property bool saved: menu.holdsAll(modelData.id)
                readonly property bool partial: menu.localIds.some(id => menu.workspace.playlistsContaining(id, menu.workspace.revision).indexOf(modelData.id) >= 0)
                Text { visible: entry.height > 68; text: entry.saved ? "Saved in" : "Recently updated"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 15; font.weight: Font.DemiBold }
                Rectangle {
                    y: entry.height - 68; width: parent.width; height: 68
                    color: hit.containsMouse ? Theme.selection : "transparent"
                    PlaylistCover { x: 4; y: 10; width: 48; height: 48; source: entry.modelData.coverUrl || ""; covers: entry.modelData.covers || [] }
                    Column {
                        x: 66; y: 11; width: parent.width - 108; spacing: 4
                        Text { width: parent.width; text: entry.modelData.name; elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 18 }
                        Text { width: parent.width; text: (entry.modelData.path ? entry.modelData.path + " · " : "") + (entry.modelData.count || 0) + " tracks"; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                    }
                    Icon { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; name: entry.saved ? "check" : entry.partial ? "minus" : "add-playlist"; color: entry.saved ? Theme.primary : Theme.textMuted; size: 20 }
                    MouseArea { id: hit; objectName: "playlistMenuEntry_" + entry.modelData.id; anchors.fill: parent; hoverEnabled: true; onClicked: menu.workspace.togglePlaylist(menu.localIds, entry.modelData.id) }
                }
            }
        }
        TextButton { id: close; anchors.bottom: parent.bottom; anchors.right: parent.right; text: "Close"; kind: "ghost"; onClicked: menu.close() }
    }
}
