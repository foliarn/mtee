import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Folder or playlist tab: heading with name and totals, sortable columns and
// Spotify-style rows, or the Artwork grid.
FocusScope {
    id: view

    required property var workspace
    required property var tab
    focus: groupIndex === workspace.activeGroup
    activeFocusOnTab: true
    property int groupIndex: 0
    property int bottomInset: 0
    property var localColumnWidths: ({})
    property string draggedColumnKey: ""
    property string dropTargetKey: ""
    property bool dropAfterTarget: false
    property bool columnDragCancelled: false

    readonly property string source: tab.kind + ":" + tab.ref
    readonly property bool modelBacked: typeof workspace.trackModelForTab === "function"
    readonly property var rows: modelBacked ? [] : workspace.tabTracks(tab.kind, tab.ref, tab.sortKey, tab.sortAscending, workspace.revision)
    readonly property var trackModel: modelBacked
        ? workspace.trackModelForTab(tab.id, tab.kind, tab.ref, tab.sortKey, tab.sortAscending)
        : rows
    readonly property var orderedIds: modelBacked ? trackModel.trackIds : rows.map((track) => track.id)
    readonly property bool artwork: tab.view === "artwork"

    // Lists handed over by Python reach QML as Qt sequences, for which
    // Array.isArray is false; a length is what identifies them.
    function asArray(value) {
        return value !== undefined && value !== null && typeof value.length === "number"
            ? Array.from(value) : null
    }

    readonly property var columns: {
        const padding = width < 600 ? 12 : 24
        const gap = width < 600 ? 10 : 16
        const actions = 104
        const fallbackOptions = [
            { key: "title", label: "Title" },
            { key: "artist", label: "Artist" },
            { key: "album", label: "Album" },
            { key: "genre", label: "Genre" },
            { key: "bpm", label: "BPM" },
            { key: "key", label: "Key" },
            { key: "duration", label: "Duration" },
            { key: "format", label: "Format" },
            { key: "filename", label: "Filename" },
            { key: "bitrate", label: "Bitrate" },
            { key: "fileCreatedAt", label: "Date created" },
            { key: "fileModifiedAt", label: "Date modified" }
        ]
        const options = view.workspace.columnOptions || fallbackOptions
        const defaults = options.length > 0
            ? options.map((option) => option.key)
            : ["title", "artist", "album", "genre", "bpm", "key", "duration", "format", "filename", "bitrate", "fileCreatedAt", "fileModifiedAt"]
        const labels = ({})
        for (const option of options)
            labels[option.key] = option.label
        const baseWidths = ({ title: 0, artist: 150, album: 150, genre: 110, bpm: 52, key: 52, duration: 70, format: 72, filename: 180, bitrate: 78, fileCreatedAt: 155, fileModifiedAt: 155 })
        const fallbackPreferences = {
            order: ["title", "artist", "fileCreatedAt", "bpm", "key", "album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"],
            hidden: ["album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"],
            widths: baseWidths,
            showArtwork: true
        }
        const preferences = view.workspace.columnPreferences || fallbackPreferences
        const configuredOrder = view.asArray(preferences.order) || defaults
        const order = configuredOrder.filter((key, index) => defaults.indexOf(key) >= 0 && configuredOrder.indexOf(key) === index)
        for (const key of defaults) {
            if (order.indexOf(key) < 0)
                order.push(key)
        }
        const hidden = view.asArray(preferences.hidden) || ["album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"]
        let keys = order.filter((key) => hidden.indexOf(key) < 0)
        if (keys.length === 0)
            keys = ["title"]
        const storedWidths = preferences.widths || ({})
        let fixedWidth = 0
        for (const key of keys) {
            if (key === "title")
                continue
            const local = Number(view.localColumnWidths[key] || 0)
            const stored = Number(storedWidths[key] || 0)
            fixedWidth += local || stored || baseWidths[key]
        }
        const titleStored = Number(view.localColumnWidths.title || storedWidths.title || 0)
        const titleWidth = titleStored || Math.max(140, width - 2 * padding - actions - gap * keys.length - fixedWidth)
        const items = keys.map((key) => {
            const local = Number(view.localColumnWidths[key] || 0)
            const stored = Number(storedWidths[key] || 0)
            return {
                key: key,
                label: labels[key] || key,
                sortKey: key,
                width: key === "title" ? titleWidth : (local || stored || baseWidths[key])
            }
        })
        let itemWidth = 0
        for (const item of items)
            itemWidth += item.width
        const totalWidth = 2 * padding + actions + gap * keys.length + itemWidth
        return {
            "padding": padding, "gap": gap, "actions": actions,
            "items": items, "keys": keys, "totalWidth": totalWidth,
            "showArtwork": preferences.showArtwork !== false
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
        return modelBacked
            ? trackModel.rowForId(selected[selected.length - 1])
            : orderedIds.indexOf(selected[selected.length - 1])
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

    function play(index) {
        if (index >= 0 && index < orderedIds.length) {
            if (modelBacked)
                workspace.playTrackFromRows(orderedIds[index], source, trackModel.rows)
            else
                workspace.playTrack(orderedIds[index], source)
        }
    }

    function revealTrack(trackId) {
        if (!modelBacked)
            return
        const index = trackModel.rowForId(trackId)
        if (index < 0)
            return
        if (artwork)
            grid.positionViewAtIndex(index, GridView.Contain)
        else
            list.positionViewAtIndex(index, ListView.Contain)
    }

    Connections {
        target: view.workspace
        ignoreUnknownSignals: true
        function onTrackRevealRequested(targetGroup, tabId, trackId) {
            if (targetGroup === view.groupIndex && view.tab && view.tab.id === tabId)
                view.revealTrack(trackId)
        }
    }

    function openPlaylistMenu(anchor, trackId) {
        const ids = workspace.selectedIds.indexOf(trackId) >= 0 ? workspace.selectedIds : [trackId]
        playlistMenu.trackIds = ids
        playlistMenu.popup(anchor, 0, anchor.height)
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Escape && view.draggedColumnKey.length > 0) {
            view.columnDragCancelled = true
            view.dropTargetKey = ""
            view.draggedColumnKey = ""
            event.accepted = true
            return
        }
        if (folderSearchField.activeFocus) {
            if (event.key === Qt.Key_Escape) {
                view.forceActiveFocus()
                event.accepted = true
            }
            return
        }
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

        MouseArea {
            anchors.fill: parent
            z: -1
            acceptedButtons: Qt.LeftButton
            onClicked: view.forceActiveFocus()
        }

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
                id: chooseColumnsButton
                objectName: "chooseColumnsButton"
                icon: "settings"
                iconSize: 18
                enabled: view.modelBacked
                tip: "Choose columns"
                onClicked: columnMenu.popup(chooseColumnsButton, 0, chooseColumnsButton.height)
            }
        }

        AppMenu {
            id: columnMenu
            objectName: "columnChooserMenu"

            AppMenuItem { text: "COLUMNS"; enabled: false }

            Instantiator {
                model: view.workspace.columnOptions
                delegate: AppMenuItem {
                    required property var modelData
                    objectName: "columnOption_" + modelData.key
                    text: modelData.label
                    checkable: true
                    checked: view.columns.keys.indexOf(modelData.key) >= 0
                    mark: checked
                    enabled: checked || view.columns.keys.length > 1
                    onTriggered: view.workspace.toggleColumn(view.tab.id, modelData.key)
                }
                onObjectAdded: (index, object) => columnMenu.insertItem(index + 1, object)
                onObjectRemoved: (index, object) => columnMenu.removeItem(object)
            }

            AppMenuSeparator {}

            AppMenuItem {
                text: "Show artwork"
                checkable: true
                checked: view.columns.showArtwork
                mark: checked
                onTriggered: view.workspace.setShowArtwork(!checked)
            }

            AppMenuItem {
                text: "Reset columns"
                onTriggered: {
                    view.localColumnWidths = ({})
                    view.workspace.resetColumns()
                }
            }
        }

        TextField {
            objectName: "folderSearchField"
            id: folderSearchField
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
            Keys.onEscapePressed: (event) => {
                view.forceActiveFocus()
                event.accepted = true
            }
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
                objectName: "trackRowsList"
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

                WheelScrollHandler {
                    flickable: list
                }

                delegate: TrackRow {
                    id: trackRow
                    objectName: "trackRow_" + (index + 1)
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

        WheelScrollHandler {
            flickable: grid
        }

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

    TrackContextMenu {
        id: contextMenu
        objectName: "trackContextMenu"
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
        readonly property bool sorted: view.tab.sortMode === "manual"
            && view.tab.sortKey === sortKey && sortKey.length > 0

        Drag.active: columnDragHandler.active
        Drag.source: cell
        Drag.keys: ["mtee-column"]
        Drag.supportedActions: Qt.MoveAction
        Drag.hotSpot.x: cell.width / 2
        Drag.hotSpot.y: cell.height / 2

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
            anchors.rightMargin: 8
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: Qt.PointingHandCursor
            onPressed: view.forceActiveFocus()
            onClicked: (event) => {
                if (event.button === Qt.RightButton)
                    reorderMenu.popup(cell, event.x, event.y)
                else if (cell.sortKey.length > 0)
                    view.workspace.setSort(view.tab.id, cell.sortKey)
            }
        }

        AppMenu {
            id: reorderMenu
            AppMenuItem {
                text: "Move left"
                onTriggered: view.workspace.moveColumn(view.tab.id, cell.columnKey, -1)
            }
            AppMenuItem {
                text: "Move right"
                onTriggered: view.workspace.moveColumn(view.tab.id, cell.columnKey, 1)
            }
        }

        DragHandler {
            id: columnDragHandler
            parent: headerMouse
            target: null
            acceptedButtons: Qt.LeftButton
            enabled: cell.columnKey.length > 0
            onActiveChanged: {
                if (active) {
                    view.draggedColumnKey = cell.columnKey
                    view.dropTargetKey = ""
                    view.columnDragCancelled = false
                } else if (view.draggedColumnKey === cell.columnKey) {
                    view.draggedColumnKey = ""
                    view.dropTargetKey = ""
                }
            }
        }

        DropArea {
            anchors.fill: parent
            keys: ["mtee-column"]

            onEntered: (drag) => {
                if (!view.columnDragCancelled && drag.source && drag.source.columnKey !== cell.columnKey) {
                    view.dropTargetKey = cell.columnKey
                    view.dropAfterTarget = drag.x >= width / 2
                }
            }
            onPositionChanged: (drag) => {
                if (!view.columnDragCancelled && drag.source && drag.source.columnKey !== cell.columnKey) {
                    view.dropTargetKey = cell.columnKey
                    view.dropAfterTarget = drag.x >= width / 2
                }
            }
            onExited: {
                if (view.dropTargetKey === cell.columnKey)
                    view.dropTargetKey = ""
            }
            onDropped: (drop) => {
                if (!view.columnDragCancelled && drop.source && drop.source.columnKey !== cell.columnKey)
                    view.workspace.moveColumnRelative(view.tab.id, drop.source.columnKey, cell.columnKey, drop.x >= width / 2)
                drop.acceptProposedAction()
                view.dropTargetKey = ""
            }
        }

        Rectangle {
            z: 3
            visible: view.draggedColumnKey.length > 0 && view.dropTargetKey === cell.columnKey
            x: view.dropAfterTarget ? parent.width - width : 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 2
            color: Theme.primary
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
                view.localColumnWidths = ({})
            }
        }
    }
}
