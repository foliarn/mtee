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
    property var localColumnWidths: ({})

    readonly property string source: tab.kind + ":" + tab.ref
    readonly property bool modelBacked: typeof workspace.trackModelForTab === "function"
    readonly property var rows: modelBacked ? [] : workspace.tabTracks(tab.kind, tab.ref, tab.sortKey, tab.sortAscending, workspace.revision)
    readonly property var trackModel: modelBacked
        ? workspace.trackModelForTab(tab.id, tab.kind, tab.ref, tab.sortKey, tab.sortAscending)
        : rows
    readonly property var orderedIds: modelBacked ? trackModel.trackIds : rows.map((track) => track.id)
    readonly property bool artwork: tab.view === "artwork"

    readonly property var columns: {
        const padding = width < 600 ? 12 : 24
        const gap = width < 600 ? 10 : 16
        const number = 28
        const actions = width < 600 ? 36 : 64
        const liveDefaults = ["title", "artist", "album", "genre", "bpm", "key", "duration", "format", "filename", "bitrate"]
        const demoDefaults = ["title", "album", "genre", "bpm", "key", "duration"]
        const defaults = view.modelBacked ? liveDefaults : demoDefaults
        const labels = ({ title: "Title", artist: "Artist", album: "Album", genre: "Genre", bpm: "BPM", key: "Key", duration: "Duration", format: "Format", filename: "Filename", bitrate: "Bitrate" })
        const baseWidths = ({ title: 0, artist: 150, album: 150, genre: 110, bpm: 52, key: 52, duration: 70, format: 72, filename: 180, bitrate: 78 })
        const configuredOrder = tab.columnOrder !== undefined && tab.columnOrder !== null
            ? Array.from(tab.columnOrder) : defaults
        const order = configuredOrder.filter((key, index) => defaults.indexOf(key) >= 0 && configuredOrder.indexOf(key) === index)
        const hidden = view.modelBacked
            ? (tab.hiddenColumns !== undefined && tab.hiddenColumns !== null
                ? Array.from(tab.hiddenColumns) : ["album", "duration", "format", "filename", "bitrate"])
            : []
        let keys = order.filter((key) => key === "title" || hidden.indexOf(key) < 0)
        if (keys.indexOf("title") < 0)
            keys.unshift("title")
        const storedWidths = tab.columnWidths || ({})
        let fixedWidth = 0
        for (const key of keys) {
            if (key === "title")
                continue
            const local = Number(view.localColumnWidths[key] || 0)
            const stored = Number(storedWidths[key] || 0)
            fixedWidth += local || stored || baseWidths[key]
        }
        const titleStored = Number(view.localColumnWidths.title || storedWidths.title || 0)
        const titleWidth = titleStored || Math.max(140, width - 2 * padding - number - actions - gap * (keys.length + 1) - fixedWidth)
        const items = keys.map((key) => {
            const local = Number(view.localColumnWidths[key] || 0)
            const stored = Number(storedWidths[key] || 0)
            return {
                key: key,
                label: labels[key],
                sortKey: key,
                width: key === "title" ? titleWidth : (local || stored || baseWidths[key])
            }
        })
        let itemWidth = 0
        for (const item of items)
            itemWidth += item.width
        const totalWidth = 2 * padding + number + actions + gap * (keys.length + 1) + itemWidth
        return {
            "padding": padding, "gap": gap, "number": number, "actions": actions,
            "items": items, "keys": keys, "totalWidth": totalWidth
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
        if (
            !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier))
            && workspace.selectedIds.indexOf(trackId) >= 0
        )
            return
        const mode = (event.modifiers & Qt.ShiftModifier) ? "range"
            : (event.modifiers & Qt.ControlModifier) ? "toggle" : "single"
        workspace.selectTrack(trackId, mode, orderedIds)
    }

    function acceptTrackDrop(sourceGroupIndex, trackIds) {
        if (
            !view.modelBacked || view.tab.kind !== "folder"
            || view.workspace.groups.length < 2 || sourceGroupIndex === view.groupIndex
            || !trackIds || typeof trackIds.length !== "number"
        )
            return false
        const ids = Array.from(trackIds, String).filter(id => id.length > 0)
        return ids.length > 0 && view.workspace.previewMoveBetweenGroups(
            sourceGroupIndex, view.groupIndex, ids, view.tab.ref
        )
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

            IconButton {
                objectName: "chooseColumnsButton"
                icon: "settings"
                iconSize: 18
                enabled: view.modelBacked
                tip: "Choose columns"
                onClicked: columnMenu.open()
            }
        }

        Menu {
            id: columnMenu
            objectName: "columnChooserMenu"

            MenuItem {
                text: "Artist"
                checkable: true
                checked: view.columns.keys.indexOf("artist") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "artist")
            }
            MenuItem {
                objectName: "columnOption_album"
                text: "Album"
                checkable: true
                checked: view.columns.keys.indexOf("album") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "album")
            }
            MenuItem {
                text: "Genre"
                checkable: true
                checked: view.columns.keys.indexOf("genre") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "genre")
            }
            MenuItem {
                text: "BPM"
                checkable: true
                checked: view.columns.keys.indexOf("bpm") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "bpm")
            }
            MenuItem {
                text: "Key"
                checkable: true
                checked: view.columns.keys.indexOf("key") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "key")
            }
            MenuSeparator {}
            MenuItem {
                text: "Duration"
                checkable: true
                checked: view.columns.keys.indexOf("duration") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "duration")
            }
            MenuItem {
                text: "Format"
                checkable: true
                checked: view.columns.keys.indexOf("format") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "format")
            }
            MenuItem {
                text: "Filename"
                checkable: true
                checked: view.columns.keys.indexOf("filename") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "filename")
            }
            MenuItem {
                text: "Bitrate"
                checkable: true
                checked: view.columns.keys.indexOf("bitrate") >= 0
                onTriggered: view.workspace.toggleColumn(view.tab.id, "bitrate")
            }
        }

        TextField {
            objectName: "folderSearchField"
            visible: view.modelBacked
            anchors.top: parent.top
            anchors.topMargin: 14
            anchors.right: parent.right
            anchors.rightMargin: view.columns.padding + 76
            width: Math.min(220, parent.width * 0.32)
            height: 28
            placeholderText: "Search this folder"
            text: view.tab.searchQuery || ""
            selectByMouse: true
            color: Theme.textPrimary
            placeholderTextColor: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            onTextEdited: view.workspace.setSearch(view.tab.id, text)
            background: Rectangle {
                color: Theme.surface
                border.width: 1
                border.color: parent.activeFocus ? Theme.focus : Theme.separator
            }
        }
    }

    Item {
        id: columnHeader
        visible: !view.artwork
        anchors.top: heading.bottom
        x: -tableViewport.contentX
        width: tableViewport.contentWidth
        height: visible ? 34 : 0

        Row {
            x: view.columns.padding
            height: parent.height
            spacing: view.columns.gap

            HeaderCell { width: view.columns.number; label: "#"; sortKey: "index"; alignRight: true }
            Repeater {
                model: view.columns.items
                HeaderCell {
                    required property var modelData
                    width: modelData.width
                    label: modelData.label
                    sortKey: modelData.sortKey
                    columnKey: modelData.key
                    alignRight: modelData.key === "bpm" || modelData.key === "duration"
                }
            }
            Item { width: view.columns.actions; height: parent.height }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            x: view.columns.padding
            width: parent.width - 2 * view.columns.padding
            height: 1
            color: Theme.separator
        }
    }

    Flickable {
        id: tableViewport
        visible: !view.artwork
        anchors.top: columnHeader.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        contentWidth: Math.max(width, view.columns.totalWidth)
        contentHeight: height

        Item {
            width: tableViewport.contentWidth
            height: tableViewport.height

            ListView {
                id: list
                anchors.fill: parent
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true
                currentIndex: -1
                highlightFollowsCurrentItem: false
                keyNavigationEnabled: false
                model: view.trackModel
                footer: Item { width: 1; height: view.bottomInset + 8 }
                ScrollBar.vertical: ThinScrollBar {}

                delegate: TrackRow {
                    id: trackRow
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    track: modelData
                    columns: view.columns
                    workspace: view.workspace
                    groupIndex: view.groupIndex
                    separateArtist: view.modelBacked
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
                        contextMenu.folderId = modelData.folder
                        contextMenu.trackIds = view.workspace.selectedIds
                        contextMenu.popup(trackRow, x, y)
                    }
                }
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
        reuseItems: true
        model: view.artwork ? view.trackModel : []
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
                source: tile.modelData.coverUrl || ""
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
                        contextMenu.folderId = tile.modelData.folder
                        contextMenu.trackIds = view.workspace.selectedIds
                        contextMenu.popup(tile, event.x, event.y)
                    }
                }
            }
        }
    }

    DropArea {
        id: moveDropArea
        objectName: "fileMoveDropArea"
        anchors.fill: parent
        z: 20
        enabled: view.modelBacked && view.tab.kind === "folder" && view.workspace.groups.length > 1
        keys: ["application/x-mtee-track-ids"]
        property bool validDrag: false

        onEntered: (drag) => {
            const source = drag.source
            validDrag = source !== null && typeof source.groupIndex !== "undefined"
                && source.workspace === view.workspace && source.groupIndex !== view.groupIndex
                && source.dragTrackIds.length > 0
        }
        onExited: validDrag = false
        onDropped: (drop) => {
            const source = drop.source
            let ids = []
            try {
                ids = JSON.parse(drop.getDataAsString("application/x-mtee-track-ids"))
            } catch (_error) {
                ids = []
            }
            if (
                validDrag && source !== null
                && view.acceptTrackDrop(Number(source.groupIndex), ids)
            )
                drop.acceptProposedAction()
            validDrag = false
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: 18
            visible: moveDropArea.validDrag
            color: Theme.surface
            opacity: 0.96
            border.width: 2
            border.color: Theme.primary

            Column {
                anchors.centerIn: parent
                spacing: 8

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Drop to preview the move"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.DemiBold
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "MTEE will show the destination and ask you to confirm."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
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
        objectName: columnKey.length > 0 ? "columnHeader_" + columnKey : ""

        property string label: ""
        property string sortKey: ""
        property string columnKey: ""
        property bool alignRight: false
        readonly property bool sorted: view.tab.sortKey === sortKey && sortKey !== "index"

        height: parent.height

        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: cell.alignRight ? parent.right : undefined
            spacing: 4
            layoutDirection: cell.alignRight ? Qt.RightToLeft : Qt.LeftToRight

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
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onClicked: (event) => {
                if (event.button === Qt.RightButton)
                    reorderMenu.open()
                else if (cell.sortKey.length > 0)
                    view.workspace.setSort(view.tab.id, cell.sortKey)
            }
        }

        Menu {
            id: reorderMenu
            MenuItem {
                text: "Move left"
                onTriggered: view.workspace.moveColumn(view.tab.id, cell.columnKey, -1)
            }
            MenuItem {
                text: "Move right"
                onTriggered: view.workspace.moveColumn(view.tab.id, cell.columnKey, 1)
            }
        }

        MouseArea {
            id: resizeHandle
            visible: view.modelBacked && cell.columnKey.length > 0
            z: 2
            width: 8
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeHorCursor
            property real startX: 0
            property int startWidth: 0

            onPressed: (mouse) => {
                startX = mouse.x
                startWidth = cell.width
            }
            onPositionChanged: (mouse) => {
                if (pressed) {
                    const resized = Math.max(44, startWidth + mouse.x - startX)
                    const next = Object.assign({}, view.localColumnWidths)
                    next[cell.columnKey] = resized
                    view.localColumnWidths = next
                }
            }
            onReleased: {
                const resized = Number(view.localColumnWidths[cell.columnKey] || cell.width)
                view.workspace.resizeColumn(view.tab.id, cell.columnKey, Math.round(resized))
            }
        }
    }
}
