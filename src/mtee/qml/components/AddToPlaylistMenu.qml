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
    width: Math.min(Theme.playlistMenuWidth, parent ? parent.width - 16 : Theme.playlistMenuWidth)
    // Title, search, "New playlist" and the margins, then the playlists as far as they fit.
    height: Math.min(Theme.playlistMenuMaxHeight, 12 * 2 + 18 + 8 + 30 + 6 + 40 + 6 + list.contentHeight)
    padding: 12
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: search.forceActiveFocus()
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
        Text { id: title; text: "Add to playlist"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary; font.weight: Font.DemiBold }
        TextField {
            id: search
            objectName: "playlistMenuSearch"
            anchors.top: title.bottom; anchors.topMargin: 8
            width: parent.width; height: 30
            leftPadding: 30
            placeholderText: "Search playlists"
            color: Theme.textPrimary; placeholderTextColor: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary
            background: Rectangle { color: Theme.chrome; radius: 5; border.color: search.activeFocus ? Theme.focus : Theme.separator }
            Icon { x: 9; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 14; color: Theme.textMuted }
        }
        Item {
            id: create
            objectName: "playlistMenuNew"
            anchors.top: search.bottom; anchors.topMargin: 6
            width: parent.width; height: 40
            Rectangle { anchors.fill: parent; radius: 4; color: createHit.containsMouse ? Theme.selection : "transparent" }
            Rectangle {
                x: 4; anchors.verticalCenter: parent.verticalCenter
                width: Theme.playlistMenuCover; height: width; radius: 4; color: Theme.selection
                Icon { anchors.centerIn: parent; name: "plus"; size: 16; color: Theme.textPrimary }
            }
            Text { x: 46; anchors.verticalCenter: parent.verticalCenter; text: "New playlist"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }
            MouseArea { id: createHit; anchors.fill: parent; hoverEnabled: true; onClicked: menu.workspace.addToNewPlaylist(menu.trackIds) }
        }
        ListView {
            id: list
            anchors.top: create.bottom; anchors.topMargin: 6
            anchors.bottom: parent.bottom
            width: parent.width
            clip: true
            model: menu.choices
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}
            delegate: Item {
                id: entry
                required property var modelData
                required property int index
                readonly property bool sectionStart: index === 0 || menu.holdsAll(modelData.id) !== menu.holdsAll(menu.choices[index - 1].id)
                width: ListView.view.width
                height: Theme.playlistMenuRow + (sectionStart ? 26 : 0)
                readonly property bool saved: menu.holdsAll(modelData.id)
                readonly property bool partial: !saved && menu.localIds.some(id => menu.workspace.playlistsContaining(id, menu.workspace.revision).indexOf(modelData.id) >= 0)
                SectionLabel { visible: entry.sectionStart; x: 4; y: 8; text: entry.saved ? "Saved in" : "Recently updated" }
                Rectangle {
                    y: entry.height - Theme.playlistMenuRow; width: parent.width; height: Theme.playlistMenuRow; radius: 4
                    color: hit.containsMouse ? Theme.selection : "transparent"
                    PlaylistCover { x: 4; anchors.verticalCenter: parent.verticalCenter; width: Theme.playlistMenuCover; height: width; source: entry.modelData.coverUrl || ""; covers: entry.modelData.covers || [] }
                    Column {
                        x: Theme.playlistMenuCover + 14; width: parent.width - Theme.playlistMenuCover - 14 - 40; anchors.verticalCenter: parent.verticalCenter; spacing: 1
                        Text { width: parent.width; text: entry.modelData.name; elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }
                        Text { width: parent.width; text: (entry.modelData.path ? entry.modelData.path + " · " : "") + (entry.modelData.count || 0) + " tracks"; elide: Text.ElideRight; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeCaption }
                    }
                    Icon { visible: !entry.partial; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; name: entry.saved ? "check" : "add-playlist"; color: entry.saved ? Theme.primary : Theme.textMuted; size: 16 }
                    Rectangle { visible: entry.partial; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 2; radius: 1; color: Theme.textSecondary }
                    MouseArea { id: hit; objectName: "playlistMenuEntry_" + entry.modelData.id; anchors.fill: parent; hoverEnabled: true; onClicked: menu.workspace.togglePlaylist(menu.localIds, entry.modelData.id) }
                }
            }
        }
    }
}
