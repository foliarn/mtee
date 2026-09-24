import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Folder or playlist tab: heading with name and totals, sortable columns and
// Spotify-style rows, or the Artwork grid.
FocusScope {
    id: view

    required property var workspace
    required property var tab
    property int groupIndex: 0
    property int bottomInset: 0

    readonly property string source: tab.kind + ":" + tab.ref
    readonly property var rows: workspace.tabTracks(tab.kind, tab.ref, tab.sortKey, tab.sortAscending, workspace.revision)
    readonly property var orderedIds: rows.map((track) => track.id)
    readonly property bool artwork: tab.view === "artwork"

    readonly property var columns: {
        const narrow = width < 600
        const padding = narrow ? 12 : 24
        const gap = narrow ? 10 : 16
        const number = 28
        const bpm = 48
        const key = 48
        const duration = 52
        const actions = narrow ? 36 : 64
        const showAlbum = width >= 880
        const showGenre = width >= 720
        const cells = 6 + (showAlbum ? 1 : 0) + (showGenre ? 1 : 0)
        const flex = Math.max(120, width - 2 * padding - number - bpm - key - duration - actions - (cells - 1) * gap)
        const title = showAlbum && showGenre ? flex * 0.46 : showAlbum || showGenre ? flex * 0.62 : flex
        return {
            "padding": padding, "gap": gap, "number": number, "bpm": bpm, "key": key,
            "duration": duration, "actions": actions, "title": title,
            "album": showAlbum ? flex * (showGenre ? 0.32 : 0.38) : 0,
            "genre": showGenre ? flex * (showAlbum ? 0.22 : 0.38) : 0
        }
    }

    objectName: "trackListView"

    function selectAll() {
        workspace.selectAll(orderedIds)
    }

    function focusedIndex() {
        const selected = workspace.selectedIds
        if (selected.length === 0)
            return -1
        return orderedIds.indexOf(selected[selected.length - 1])
    }

    function press(index, event) {
        workspace.setActiveGroup(groupIndex)
        list.currentIndex = index
        view.forceActiveFocus()
        const trackId = orderedIds[index]
        if (event.button === Qt.RightButton) {
            if (workspace.selectedIds.indexOf(trackId) < 0)
                workspace.selectTrack(trackId, "single", [])
            return
        }
        const mode = (event.modifiers & Qt.ShiftModifier) ? "range"
            : (event.modifiers & Qt.ControlModifier) ? "toggle" : "single"
        workspace.selectTrack(trackId, mode, orderedIds)
    }

    function play(index) {
        if (index >= 0 && index < orderedIds.length)
            workspace.playTrack(orderedIds[index], source)
    }

    function openPlaylistMenu(anchor, trackId) {
        const ids = workspace.selectedIds.indexOf(trackId) >= 0 ? workspace.selectedIds : [trackId]
        playlistMenu.trackIds = ids
        playlistMenu.popup(anchor, 0, anchor.height)
    }

    Keys.onPressed: (event) => {
        const count = orderedIds.length
        if (count === 0)
            return
        if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
            const start = list.currentIndex < 0 ? focusedIndex() : list.currentIndex
            const next = Math.max(0, Math.min(count - 1, start + (event.key === Qt.Key_Down ? 1 : -1)))
            list.currentIndex = next
            workspace.selectTrack(orderedIds[next], (event.modifiers & Qt.ShiftModifier) ? "range" : "single", orderedIds)
            list.positionViewAtIndex(next, ListView.Contain)
            event.accepted = true
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            play(list.currentIndex < 0 ? focusedIndex() : list.currentIndex)
            event.accepted = true
        } else if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
            selectAll()
            event.accepted = true
        }
    }

    Item {
        id: heading
        width: parent.width
        height: 92

        Column {
            x: view.columns.padding
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            spacing: 2

            SectionLabel {
                text: view.tab.kind === "playlist" ? "Playlist" : "Folder"
            }

            Row {
                spacing: 14

                Text {
                    id: name
                    text: view.tab.title
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                }

                Text {
                    anchors.baseline: name.baseline
                    text: view.workspace.tabSummary(view.tab.kind, view.tab.ref, view.workspace.revision)
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: view.columns.padding - 6
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            spacing: 2

            IconButton {
                icon: "list"
                iconSize: 18
                active: !view.artwork
                tip: "List"
                onClicked: view.workspace.setTabView(view.tab.id, "list")
            }

            IconButton {
                icon: "grid"
                iconSize: 18
                active: view.artwork
                tip: "Artwork"
                onClicked: view.workspace.setTabView(view.tab.id, "artwork")
            }
        }
    }

    Item {
        id: columnHeader
        visible: !view.artwork
        anchors.top: heading.bottom
        width: parent.width
        height: visible ? 34 : 0

        Row {
            x: view.columns.padding
            height: parent.height
            spacing: view.columns.gap

            HeaderCell { width: view.columns.number; label: "#"; sortKey: "index"; alignRight: true }
            HeaderCell { width: view.columns.title; label: "Title"; sortKey: "title" }
            HeaderCell { width: view.columns.album; visible: width > 0; label: "Album"; sortKey: "album" }
            HeaderCell { width: view.columns.genre; visible: width > 0; label: "Genre"; sortKey: "genre" }
            HeaderCell { width: view.columns.bpm; label: "BPM"; sortKey: "bpm"; alignRight: true }
            HeaderCell { width: view.columns.key; label: "Key"; sortKey: "key"; centered: true }
            HeaderCell { width: view.columns.duration; label: ""; sortKey: "duration"; alignRight: true; icon: "clock" }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            x: view.columns.padding
            width: parent.width - 2 * view.columns.padding
            height: 1
            color: Theme.separator
        }
    }

    ListView {
        id: list
        visible: !view.artwork
        anchors.top: columnHeader.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        currentIndex: -1
        highlightFollowsCurrentItem: false
        keyNavigationEnabled: false
        model: view.rows
        footer: Item { width: 1; height: view.bottomInset + 8 }
        ScrollBar.vertical: ThinScrollBar {}

        delegate: TrackRow {
            id: trackRow
            required property var modelData
            required property int index
            width: ListView.view.width
            track: modelData
            columns: view.columns
            selected: view.workspace.selectedIds.indexOf(modelData.id) >= 0
            playing: view.workspace.playingId === modelData.id
            paused: !view.workspace.isPlaying
            current: view.activeFocus && list.currentIndex === index
            inPlaylist: view.workspace.playlistsContaining(modelData.id, view.workspace.revision).length > 0
            onPressed: (event) => view.press(index, event)
            onActivated: view.play(index)
            onToggleRequested: view.workspace.togglePlay()
            onInfoRequested: {
                view.workspace.selectTrack(modelData.id, "single", [])
                view.workspace.showRightPanel("info")
            }
            onPlaylistRequested: (anchor) => view.openPlaylistMenu(anchor, modelData.id)
            onContextRequested: (x, y) => {
                contextMenu.trackId = modelData.id
                contextMenu.trackIds = view.workspace.selectedIds
                contextMenu.popup(trackRow, x, y)
            }
        }
    }

    GridView {
        id: grid
        visible: view.artwork
        anchors.top: heading.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: view.columns.padding - 8
        anchors.rightMargin: view.columns.padding - 8
        readonly property int perRow: Math.max(2, Math.floor(width / 196))
        cellWidth: Math.floor(width / perRow)
        cellHeight: cellWidth + 58
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: view.artwork ? view.rows : []
        footer: Item { width: 1; height: view.bottomInset + 8 }
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: tile
            required property var modelData
            required property int index
            readonly property bool selected: view.workspace.selectedIds.indexOf(modelData.id) >= 0
            readonly property bool playing: view.workspace.playingId === modelData.id

            width: grid.cellWidth
            height: grid.cellHeight
            color: selected ? Theme.selection : tileMouse.containsMouse ? Theme.surface : "transparent"

            CoverArt {
                id: art
                x: 8
                y: 8
                width: tile.width - 16
                height: width
                pattern: tile.modelData.cover
            }

            Column {
                anchors.top: art.bottom
                anchors.topMargin: 8
                x: 8
                width: tile.width - 16
                spacing: 2

                Text {
                    width: parent.width
                    text: tile.modelData.title
                    elide: Text.ElideRight
                    color: tile.playing ? Theme.primary : Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    width: parent.width
                    text: tile.modelData.artist.length > 0 ? tile.modelData.artist : "Unknown artist"
                    elide: Text.ElideRight
                    color: tile.modelData.artist.length > 0 ? Theme.textSecondary : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }

            MouseArea {
                id: tileMouse
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onPressed: (event) => view.press(tile.index, event)
                onDoubleClicked: view.play(tile.index)
                onClicked: (event) => {
                    if (event.button === Qt.RightButton) {
                        contextMenu.trackId = tile.modelData.id
                        contextMenu.trackIds = view.workspace.selectedIds
                        contextMenu.popup(tile, event.x, event.y)
                    }
                }
            }
        }
    }

    TrackContextMenu {
        id: contextMenu
        workspace: view.workspace
        source: view.source
    }

    AddToPlaylistMenu {
        id: playlistMenu
        workspace: view.workspace
    }

    component HeaderCell: Item {
        id: cell

        property string label: ""
        property string sortKey: ""
        property string icon: ""
        property bool alignRight: false
        property bool centered: false
        readonly property bool sorted: view.tab.sortKey === sortKey && sortKey !== "index"

        height: parent.height

        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: cell.alignRight ? parent.right : undefined
            anchors.horizontalCenter: cell.centered ? parent.horizontalCenter : undefined
            spacing: 4
            layoutDirection: cell.alignRight ? Qt.RightToLeft : Qt.LeftToRight

            Icon {
                visible: cell.icon.length > 0
                anchors.verticalCenter: parent.verticalCenter
                name: cell.icon
                size: 16
                color: cell.sorted || headerMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
            }

            Text {
                visible: cell.label.length > 0
                anchors.verticalCenter: parent.verticalCenter
                text: cell.label
                color: cell.sorted || headerMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Icon {
                visible: cell.sorted
                anchors.verticalCenter: parent.verticalCenter
                name: view.tab.sortAscending ? "arrow-up" : "arrow-down"
                size: 12
                color: Theme.primary
            }
        }

        MouseArea {
            id: headerMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: view.workspace.setSort(view.tab.id, cell.sortKey)
        }
    }
}
