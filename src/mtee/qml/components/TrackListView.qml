import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import Mtee
import "columns.js" as Columns

// Folder or playlist tab: heading with name and totals, sortable columns and
// Spotify-style rows, or the Artwork grid.
FocusScope {
    id: view

    required property var workspace
    required property var tab
    clip: true
    focus: groupId === workspace.activeGroup
    activeFocusOnTab: true
    property string groupId: ""
    property int bottomInset: 0
    property var localColumnWidths: ({})
    property string draggedColumnKey: ""
    property string dropTargetKey: ""
    property bool dropAfterTarget: false
    property bool columnDragCancelled: false
    property bool trackDragActive: false
    property var trackDragSource: null
    property string dragTitle: ""
    property string dragArtist: ""
    property int dragCount: 0
    property real dragX: 0
    property real dragY: 0
    property string dropBefore: ""
    property int dropIndex: -1
    property bool trackDropAfter: false

    readonly property string source: tab.kind + ":" + tab.ref
    readonly property bool modelBacked: typeof workspace.trackModelForTab === "function"
    readonly property var rows: modelBacked ? [] : workspace.tabTracks(tab.kind, tab.ref, tab.sortKey, tab.sortAscending, workspace.revision)
    readonly property var trackModel: modelBacked
        ? workspace.trackModelForTab(tab.id, tab.kind, tab.ref, tab.sortKey, tab.sortAscending, groupId)
        : rows
    readonly property var orderedIds: modelBacked ? trackModel.trackIds : rows.map((track) => track.id)
    readonly property var selectionIds: {
        workspace.selectedIds
        return workspace.selectedIdsForGroup(groupId)
    }
    // id -> true, built once per selection change, so each row looks up its neighbours in O(1).
    readonly property var selectionSet: {
        const set = ({})
        for (let i = 0; i < selectionIds.length; ++i)
            set[selectionIds[i]] = true
        return set
    }
    // An empty selection also drops the keyboard cursor, so no row keeps its focus frame.
    onSelectionIdsChanged: {
        if (selectionIds.length === 0)
            list.currentIndex = -1
    }
    // A track list of a plugin tab kind is laid out like a playlist, with its own saved columns.
    readonly property var pluginUi: workspace.pluginUi || null
    readonly property bool isPluginList: modelBacked && pluginUi !== null && pluginUi.isTrackList(tab.kind)
    readonly property bool isPlaylist: (tab.kind === "playlist" || isPluginList) && modelBacked
    // The kind that decides which plugin columns start visible.
    readonly property string columnKind: isPluginList ? tab.kind : "playlist"
    readonly property bool isArtist: tab.kind === "artist" && modelBacked
    // The plugin's name on the right of its column: its title, with " plugin" added unless the
    // title already ends with the word "plugin" ("Sample plugin", not "Sample plugin plugin").
    function pluginHint(title) {
        const name = String(title).trim()
        return /(^|\W)plugin$/i.test(name) ? name : name + " plugin"
    }
    property bool playlistSearchOpen: false
    property bool folderSearchOpen: false
    readonly property var playlistOptions: ["title", "artist", "album", "bpm", "key", "duration"]
    readonly property bool artwork: tab.view === "artwork"
    // A playlist or folder list scrolls as one page: the heading moves up with the rows and only the
    // column row sticks. The heading is one item, moved by the list's scroll; it is never reparented.
    readonly property bool scrollHeading: !view.artwork && !view.isArtist
    // "Hide tracks not on this device" is offered only while a plugin provides availability.
    readonly property bool availabilityFilterOffered: workspace.availabilityProvided === true
    // Tracks the filter leaves out of this list; the meta line says so.
    readonly property int hiddenCount: modelBacked ? (trackModel.hiddenCount || 0) : 0

    // Lists handed over by Python reach QML as Qt sequences, for which
    // Array.isArray is false; a length is what identifies them.
    function asArray(value) {
        return value !== undefined && value !== null && typeof value.length === "number"
            ? Array.from(value) : null
    }

    // The saved layout of a playlist or plugin list (read again when the plugins' revision moves).
    readonly property var playlistPreferences: !isPlaylist ? null
        : isPluginList ? pluginUi.tabColumns(tab.kind, pluginUi.revision) : workspace.playlistModel.columns

    function savePlaylistColumns(prefs) {
        if (isPluginList)
            pluginUi.setTabColumns(tab.kind, prefs)
        else
            workspace.playlistModel.setColumns(prefs)
    }

    readonly property var columns: {
        const padding = width < 600 ? 12 : 24
        const gap = width < 600 ? 10 : 16
        const playSlot = 32
        const actions = 140
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
        // Plugin columns can be shown in any playlist and in the lists of plugins.
        const pluginOptions = view.isPlaylist && view.pluginUi !== null ? view.pluginUi.columnOptions : []
        const options = (view.workspace.columnOptions || fallbackOptions)
            .filter(o => !view.isPlaylist || view.playlistOptions.indexOf(o.key) >= 0)
            .concat(pluginOptions)
        const defaults = options.length > 0
            ? options.map((option) => option.key)
            : ["title", "artist", "album", "genre", "bpm", "key", "duration", "format", "filename", "bitrate", "fileCreatedAt", "fileModifiedAt"]
        const labels = ({})
        for (const option of options)
            labels[option.key] = option.label
        const baseWidths = ({ title: 0, artist: 150, album: 150, genre: 110, bpm: 52, key: 52, duration: 70, format: 72, filename: 180, bitrate: 78, fileCreatedAt: 110, fileModifiedAt: 110 })
        const fallbackPreferences = {
            order: ["title", "artist", "fileCreatedAt", "bpm", "key", "album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"],
            hidden: ["album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"],
            widths: baseWidths,
            showArtwork: true
        }
        for (const option of pluginOptions)
            baseWidths[option.key] = option.width
        const preferences = view.playlistPreferences !== null ? view.playlistPreferences : (view.workspace.columnPreferences || fallbackPreferences)
        const configuredOrder = view.asArray(preferences.order) || defaults
        const order = configuredOrder.filter((key, index) => defaults.indexOf(key) >= 0 && configuredOrder.indexOf(key) === index)
        for (const key of defaults) {
            if (order.indexOf(key) < 0)
                order.push(key)
        }
        const hidden = view.isPlaylist && view.pluginUi !== null
            ? view.asArray(view.pluginUi.hiddenColumns(view.columnKind, preferences)) || []
            : view.asArray(preferences.hidden) || ["album", "genre", "duration", "format", "filename", "bitrate", "fileModifiedAt"]
        let keys = order.filter((key) => hidden.indexOf(key) < 0)
        if (keys.length === 0)
            keys = ["title"]
        const storedWidths = preferences.widths || ({})
        // The widths the visible columns ask for. Title without a width of its own is automatic.
        const wanted = keys.map((key) => {
            const local = Number(view.localColumnWidths[key] || 0)
            const stored = Number(storedWidths[key] || 0)
            const preferred = key === "title"
                ? Number(view.localColumnWidths.title || storedWidths.title || 0)
                : (local || stored || baseWidths[key])
            return { key: key, width: preferred }
        })
        // The room between the play slot and the action cell. Columns that do not fit leave from the
        // right for this render only (columns.js); the saved preferences keep them. A border drag
        // changes the widths inside this room (resizeBoundary), so it never runs past the edge.
        const region = width - 2 * padding - playSlot - actions
        const fit = Columns.fitColumns(wanted, region, gap)
        const items = fit.items.map((item) => ({
            key: item.key,
            label: labels[item.key] || item.key,
            sortKey: item.key,
            width: item.width
        }))
        return {
            "padding": padding, "gap": gap, "playSlot": playSlot, "actions": actions,
            "items": items, "keys": keys, "hiddenByWidth": fit.hidden,
            // The room the column widths share, the gaps excluded (for resizeBoundary).
            "room": region - (items.length + 1) * gap,
            "defaults": baseWidths,
            "actionsX": Columns.actionsLeft(items, width, padding, playSlot, actions, gap),
            "showArtwork": preferences.showArtwork !== false
        }
    }

    objectName: "trackListView"

    function selectAll() {
        workspace.selectAll(orderedIds)
    }

    // Indexing the model-backed id list from QML re-reads it for every step, so ask the model.
    function indexOfTrack(trackId) {
        return modelBacked ? trackModel.rowForId(trackId) : orderedIds.indexOf(trackId)
    }

    function focusedIndex() {
        const selected = selectionIds
        if (selected.length === 0)
            return -1
        return indexOfTrack(selected[selected.length - 1])
    }

    function press(index, event) {
        workspace.focusGroup(groupId)
        list.currentIndex = index
        view.forceActiveFocus()
        const trackId = orderedIds[index]
        if (event.button === Qt.RightButton) {
            if (selectionIds.indexOf(trackId) < 0)
                workspace.selectTrack(trackId, "single", [])
            return
        }
        if (
            !(event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier))
            && selectionIds.indexOf(trackId) >= 0
        )
            return
        const mode = (event.modifiers & Qt.ShiftModifier) ? "range"
            : (event.modifiers & Qt.ControlModifier) ? "toggle" : "single"
        workspace.selectTrack(trackId, mode, orderedIds)
    }

    // A plain click that ends without a drag collapses a multi-row selection to the clicked row.
    function clickTrack(index, event) {
        if (event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier))
            return
        const trackId = orderedIds[index]
        if (selectionIds.length > 1 && selectionIds.indexOf(trackId) >= 0)
            workspace.selectTrack(trackId, "single", [])
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
            if (targetGroup === view.groupId && view.tab && view.tab.id === tabId)
                view.revealTrack(trackId)
        }
    }

    function openPlaylistMenu(anchor, trackId) {
        const ids = selectionIds.indexOf(trackId) >= 0 ? selectionIds : [trackId]
        playlistMenu.trackIds = ids
        playlistMenu.popup(anchor, 0, anchor.height)
    }

    // One Python call for the model-backed list: walking its rows from QML is quadratic.
    function dragPayload(selected) {
        if (view.modelBacked)
            return view.trackModel.dragPayload(selected, view.isPlaylist)
        const chosen = Array.from(view.rows).filter(row => selected.indexOf(row.id) >= 0)
        const trackIds = chosen.map(row => view.isPlaylist ? row.trackId : row.id).filter(Boolean)
        return {
            entryIds: chosen.map(row => row.entryId || "").filter(Boolean),
            trackIds: trackIds,
            canAdd: trackIds.length === chosen.length && chosen.every(row => row.available !== false),
            count: chosen.length,
            title: chosen.length ? String(chosen[0].title) : "",
            artist: chosen.length ? String(chosen[0].artist) : ""
        }
    }

    function prepareTrackDrag(item, track) {
        const selected = selectionIds.indexOf(track.id) >= 0 ? selectionIds : [track.id]
        const payload = dragPayload(selected)
        item.dragEntryIds = payload.entryIds
        item.dragTrackIds = payload.trackIds
        item.dragCanAdd = payload.canAdd
        item.dragSource = view.source
        item.dragVersion = view.isPlaylist && !view.isPluginList ? Number(view.workspace.playlistModel.details(view.tab.ref).version) : -1
        item.dragPrepared = true
        dragSession.dragTrackIds = item.dragTrackIds
        dragSession.dragEntryIds = item.dragEntryIds
        dragSession.dragCanAdd = item.dragCanAdd
        dragSession.dragSource = item.dragSource
        dragSession.dragVersion = item.dragVersion
        view.trackDragSource = item
        view.trackDragActive = true
        view.dragCount = payload.count
        view.dragTitle = payload.count ? payload.title : track.title
        view.dragArtist = payload.count ? payload.artist : track.artist
    }

    function moveTrackDrag(item, x, y) {
        const point = item.mapToItem(view, x, y)
        view.dragX = point.x
        view.dragY = point.y
    }

    function endTrackDrag() {
        view.trackDragActive = false
        view.trackDragSource = null
        view.dropIndex = -1
        view.dropBefore = ""
    }
    function finishTrackDrag(item) {
        const held = item && item.dragModifiers !== undefined ? item.dragModifiers : 0
        dragSession.dragModifiers = held | (view.ctrlDown ? Qt.ControlModifier : 0)
        if (view.trackDragActive) {
            if (item && item.dragCancelled) dragSession.Drag.cancel()
            else dragSession.Drag.drop()
        }
        view.endTrackDrag()
    }
    function cancelTrackDrag() {
        if (view.trackDragSource) view.trackDragSource.dragCancelled = true
        if (view.trackDragActive) dragSession.Drag.cancel()
        view.endTrackDrag()
    }

    Component.onDestruction: cancelTrackDrag()
    Connections {
        target: view.Window.window
        function onActiveChanged() {
            if (!view.Window.window.active) view.cancelTrackDrag()
        }
    }
    Timer {
        interval: 35
        repeat: true
        running: view.trackDragActive
        onTriggered: {
            const scroller = view.artwork ? grid : list
            const point = view.mapToItem(scroller, view.dragX, view.dragY)
            if (point.y < 28 && point.y >= -12)
                scroller.contentY = Math.max(0, scroller.contentY - 12)
            else if (point.y > scroller.height - 28 && point.y <= scroller.height + 12)
                scroller.contentY = Math.min(Math.max(0, scroller.contentHeight - scroller.height), scroller.contentY + 12)
        }
    }

    function canReorderDrag(item) {
        return item && view.isPlaylist && view.tab.ref !== "liked"
            && item.dragSource === view.source && item.dragEntryIds.length > 0
            && !view.tab.searchQuery && view.tab.sortKey === "index"
    }

    // Ctrl+C, Ctrl+X and Ctrl+V on the tracks of this list. Returns whether the key was used; a
    // text field with the focus keeps its own copy and paste.
    function clipboardKey(key) {
        if (typeof workspace.setTrackClipboard !== "function")
            return false
        const focused = view.Window.activeFocusItem
        if (focused && focused.cursorPosition !== undefined)
            return false
        if (key === Qt.Key_V) {
            workspace.pasteTracks(tab.kind, tab.ref)
            return true
        }
        if (selectionIds.length === 0)
            return false
        const payload = dragPayload(selectionIds)
        if (payload.trackIds.length === 0)
            return false
        workspace.setTrackClipboard(payload.trackIds, payload.entryIds, view.source, key === Qt.Key_X)
        return true
    }

    // The tracks of another list can land on this one: on a playlist they are added, on a folder
    // list the files are moved (copied with Ctrl). A list that reorders its own entries, or the
    // list the tracks come from, leaves the drag to the rows.
    function acceptsTrackDrop(item) {
        if (!item || item.dragCanAdd !== true || item.dragTrackIds.length === 0)
            return false
        if (item.dragSource === view.source || view.isPluginList)
            return false
        if (view.tab.kind === "playlist")
            return view.tab.ref !== "liked"
        return view.tab.kind === "folder"
    }

    function setDropBoundary(index, after) {
        view.dropIndex = index
        view.trackDropAfter = after
        view.dropBefore = after ? (index + 1 < view.orderedIds.length ? view.orderedIds[index + 1] : "") : view.orderedIds[index]
    }

    TrackDragPreview {
        id: dragPreview
        parent: Overlay.overlay
        visible: view.trackDragActive
        trackTitle: view.dragTitle
        artist: view.dragArtist
        count: view.dragCount
        readonly property var pointer: view.mapToItem(parent, view.dragX, view.dragY)
        x: Math.max(8, Math.min(parent.width - width - 8, pointer.x + 16))
        y: Math.max(8, Math.min(parent.height - height - 8, pointer.y + 16))
    }
    Item {
        id: dragSession
        parent: Overlay.overlay
        width: 1; height: 1
        readonly property var pointer: view.mapToItem(parent, view.dragX, view.dragY)
        x: pointer.x; y: pointer.y
        property var dragTrackIds: []
        property var dragEntryIds: []
        property string dragSource: ""
        property int dragVersion: -1
        property bool dragCanAdd: false
        // The keys held when the pointer was released (Ctrl on a folder list copies the files).
        property int dragModifiers: 0
        Drag.active: view.trackDragActive
        Drag.source: dragSession
        Drag.keys: ["mtee-tracks", "mtee-playlist-entry"]
        Drag.supportedActions: Qt.CopyAction | Qt.MoveAction
    }

    // Tracks dragged from another list: the whole list is the target (see acceptsTrackDrop).
    DropArea {
        id: listDrop
        objectName: "trackListDrop"
        anchors.fill: parent
        z: 50
        keys: ["mtee-tracks"]
        enabled: typeof view.workspace.dropTracksOnList === "function"
        onEntered: drag => { drag.accepted = view.acceptsTrackDrop(drag.source) }
        onDropped: drop => {
            if (!view.acceptsTrackDrop(drop.source))
                return
            const copy = (drop.source.dragModifiers & Qt.ControlModifier) !== 0
            view.workspace.dropTracksOnList(drop.source.dragTrackIds, drop.source.dragSource,
                view.tab.kind, view.tab.ref, copy)
        }
        Rectangle {
            anchors.fill: parent
            visible: listDrop.containsDrag
            color: "transparent"
            border.width: 2
            border.color: Theme.primary
        }
    }

    // Whether Ctrl is held, read when a drag is released (the pointer events of some devices do not
    // carry the modifiers). Ctrl on a folder list copies the dropped files instead of moving them.
    property bool ctrlDown: false
    onActiveFocusChanged: if (!activeFocus) ctrlDown = false
    Keys.onReleased: (event) => {
        if (event.key === Qt.Key_Control)
            view.ctrlDown = false
    }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Control)
            view.ctrlDown = true
        if (event.key === Qt.Key_Escape && view.trackDragActive) {
            view.cancelTrackDrag()
            event.accepted = true
            return
        }
        if (event.key === Qt.Key_Escape && view.draggedColumnKey.length > 0) {
            view.columnDragCancelled = true
            view.dropTargetKey = ""
            view.draggedColumnKey = ""
            event.accepted = true
            return
        }
        // The search field of a folder handles its own keys (Esc clears it).
        if (folderSearch.fieldActive)
            return
        if (event.key === Qt.Key_Escape && !playlistSearch.fieldActive) {
            workspace.clearSelection(view.groupId)
            event.accepted = true
            return
        }
        if ((event.modifiers & Qt.ControlModifier) && !playlistSearch.fieldActive
                && (event.key === Qt.Key_C || event.key === Qt.Key_X || event.key === Qt.Key_V)
                && view.clipboardKey(event.key)) {
            event.accepted = true
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
        // Above the rows' viewport, which starts at the top of the page in a scrolling list.
        z: 3
        y: view.scrollHeading ? -list.scrolledY : 0
        height: view.isPlaylist ? (playlistHeader.item ? playlistHeader.item.implicitHeight : 330)
            : view.isArtist ? (artistHeader.item ? artistHeader.item.implicitHeight : 330) : 92

        // The wheel over the heading scrolls the page like the wheel over the rows.
        WheelHandler {
            enabled: view.scrollHeading
            target: null
            blocking: false
            onWheel: (event) => {
                const low = list.originY
                const high = Math.max(low, list.originY + list.contentHeight - list.height)
                list.contentY = Math.max(low, Math.min(high, list.contentY - event.angleDelta.y / 120 * 72))
            }
        }

        MouseArea {
            anchors.fill: parent
            z: -1
            acceptedButtons: Qt.LeftButton
            onClicked: { view.forceActiveFocus(); view.workspace.clearSelection(view.groupId) }
        }

        Loader {
            id: playlistHeader
            anchors.fill: parent
            active: view.isPlaylist
            sourceComponent: Component { PlaylistHeader { workspace: view.workspace; tab: view.tab; trackModel: view.trackModel } }
        }
        Loader {
            id: artistHeader
            anchors.fill: parent
            active: view.isArtist
            // The artist manager plugin (behind the plugin switch) keeps its own header.
            sourceComponent: typeof view.workspace.isPluginArtistPage === "function"
                && view.workspace.isPluginArtistPage(view.tab.ref) ? pluginArtistHeader : artistPageHeader
        }
        Component { id: artistPageHeader; ArtistPageHeader { workspace: view.workspace; tab: view.tab; trackModel: view.trackModel } }
        Component { id: pluginArtistHeader; ArtistHeader { workspace: view.workspace; tab: view.tab; trackModel: view.trackModel } }
        Column {
            visible: !view.isPlaylist && !view.isArtist
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
                        + (view.hiddenCount > 0 ? " · " + view.hiddenCount + " hidden" : "")
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
            // On a playlist the controls are on the Play row, centred on the Play button (56 px,
            // 24 from the bottom of the header).
            anchors.bottomMargin: view.isPlaylist ? 24 + Math.max(0, (56 - implicitHeight) / 2)
                : view.isArtist ? 36 : 14
            spacing: 2

            SearchField {
                id: playlistSearch
                visible: view.isPlaylist
                open: view.playlistSearchOpen
                onOpenChanged: view.playlistSearchOpen = open
                expandedWidth: Math.min(220, view.width * 0.25)
                fieldObjectName: "playlistSearchField"
                buttonObjectName: "playlistSearchButton"
                placeholder: "Search this playlist"
                tip: "Search playlist"
                text: view.tab.searchQuery || ""
                onEdited: (text) => {
                    view.workspace.focusGroup(view.groupId)
                    view.workspace.setSearch(view.tab.id, text)
                }
            }
            IconButton {
                icon: "list"
                iconSize: 18
                active: !view.artwork
                tip: "List"
                onClicked: {
                    view.workspace.focusGroup(view.groupId)
                    view.workspace.setTabView(view.tab.id, "list")
                }
            }

            IconButton {
                icon: "grid"
                iconSize: 18
                active: view.artwork
                tip: "Artwork"
                onClicked: {
                    view.workspace.focusGroup(view.groupId)
                    view.workspace.setTabView(view.tab.id, "artwork")
                }
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

            SearchField {
                id: folderSearch
                visible: view.modelBacked && !view.isPlaylist
                open: view.folderSearchOpen
                onOpenChanged: view.folderSearchOpen = open
                expandedWidth: Math.min(220, view.width * 0.25)
                fieldObjectName: "folderSearchField"
                buttonObjectName: "folderSearchButton"
                placeholder: view.isArtist ? "Search this artist" : "Search this folder"
                tip: view.isArtist ? "Search artist" : "Search folder"
                text: view.tab.searchQuery || ""
                onEdited: (text) => {
                    view.workspace.focusGroup(view.groupId)
                    view.workspace.setSearch(view.tab.id, text)
                }
            }

            IconButton {
                id: moreButton
                objectName: "moreButton"
                icon: "more"
                iconSize: 18
                enabled: view.modelBacked
                tip: "More"
                onClicked: moreMenu.popup(moreButton, 0, moreButton.height)
            }
        }

        AppMenu {
            id: columnMenu
            objectName: "columnChooserMenu"

            AppMenuItem { text: "COLUMNS"; enabled: false }

            Instantiator {
                // The core columns, then the columns of plugins with the plugin's name on the right.
                model: view.workspace.columnOptions
                    .filter(o => !view.isPlaylist || view.playlistOptions.indexOf(o.key) >= 0)
                    .concat(view.isPlaylist && view.pluginUi !== null ? view.pluginUi.columnOptions : [])
                delegate: AppMenuItem {
                    required property var modelData
                    objectName: "columnOption_" + modelData.key
                    text: modelData.label
                    // A column hidden for lack of room stays checked; the hint says why it is not drawn.
                    hint: view.columns.hiddenByWidth.indexOf(modelData.key) >= 0 ? "not enough room"
                        : modelData.plugin ? view.pluginHint(modelData.plugin) : ""
                    checkable: true
                    checked: view.columns.keys.indexOf(modelData.key) >= 0
                    mark: checked
                    enabled: view.isPlaylist ? (!checked || view.columns.keys.length > 1) : checked || view.columns.keys.length > 1
                    onTriggered: {
                        if (view.isPlaylist && modelData.plugin) {
                            view.savePlaylistColumns(view.pluginUi.toggledColumns(view.columnKind, view.playlistPreferences, modelData.key))
                        } else if (view.isPlaylist) {
                            const prefs = Object.assign({}, view.playlistPreferences)
                            let hidden = Array.from(prefs.hidden)
                            if (hidden.indexOf(modelData.key) >= 0) hidden = hidden.filter(k => k !== modelData.key)
                            else if (hidden.length < 5) hidden.push(modelData.key)
                            prefs.hidden = hidden
                            view.savePlaylistColumns(prefs)
                        } else view.workspace.toggleColumn(view.tab.id, modelData.key)
                    }
                }
                onObjectAdded: (index, object) => columnMenu.insertItem(index + 1, object)
                onObjectRemoved: (index, object) => columnMenu.removeItem(object)
            }

            AppMenuSeparator {}

            AppMenuItem {
                text: "FILTER"
                enabled: false
                visible: view.availabilityFilterOffered
                height: visible ? implicitHeight : 0
            }

            AppMenuItem {
                objectName: "hideNotOnDevice"
                text: "Hide tracks not on this device"
                visible: view.availabilityFilterOffered
                height: visible ? implicitHeight : 0
                // The choice is read from the workspace, not from the item: a checkable item
                // flips its own check before it reports the trigger.
                mark: view.workspace.hideNotOnDevice === true
                onTriggered: view.workspace.setHideNotOnDevice(view.workspace.hideNotOnDevice !== true)
            }

            AppMenuSeparator {
                visible: view.availabilityFilterOffered
                height: visible ? implicitHeight : 0
            }

        }

        // The other menu: the list's own options, apart from the columns (plan 133.6).
        AppMenu {
            id: moreMenu
            objectName: "moreMenu"

            AppMenuItem {
                objectName: "customOrderAction"
                text: "Custom order"
                visible: view.isPlaylist && !view.isPluginList
                height: visible ? implicitHeight : 0
                onTriggered: view.workspace.customPlaylistOrder(view.tab.id)
            }

            AppMenuSeparator {
                visible: view.isPlaylist && !view.isPluginList
                height: visible ? implicitHeight : 0
            }

            AppMenuItem {
                objectName: "showArtworkAction"
                text: "Show artwork"
                checkable: true
                checked: view.columns.showArtwork
                mark: checked
                onTriggered: {
                    if (view.isPlaylist) {
                        const prefs = Object.assign({}, view.playlistPreferences)
                        prefs.showArtwork = !checked
                        view.savePlaylistColumns(prefs)
                    } else view.workspace.setShowArtwork(!checked)
                }
            }

            AppMenuSeparator {}

            AppMenuItem {
                objectName: "resetColumnsAction"
                text: "Reset columns"
                onTriggered: {
                    view.localColumnWidths = ({})
                    if (view.isPluginList) view.pluginUi.resetTabColumns(view.tab.kind)
                    else if (view.isPlaylist) view.workspace.playlistModel.resetColumns()
                    else view.workspace.resetColumns()
                }
            }
        }

    }

    Item {
        id: columnHeader
        visible: !view.artwork
        // Under the heading; in a scrolling list it sticks to the top once the heading has scrolled away.
        y: view.scrollHeading ? Math.max(0, heading.height - list.scrolledY) : heading.height
        z: 2
        width: view.width
        height: visible ? 34 : 0

        // Solid, so that the rows do not show through the sticky columns (plan 135).
        Rectangle {
            objectName: "columnHeaderBackground"
            anchors.fill: parent
            color: Theme.windowSurface
        }

        Row {
            x: view.columns.padding
            height: parent.height
            spacing: view.columns.gap

            Text {
                width: view.columns.playSlot
                height: parent.height
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: "#"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Repeater {
                // Driven by the column count only: a model rebuilt on every width change would
                // destroy the resize handle, and with it the pointer grab, in the middle of a drag.
                model: view.columns.items.length
                HeaderCell {
                    required property int index
                    readonly property var spec: index < view.columns.items.length
                        ? view.columns.items[index]
                        : ({ key: "", label: "", sortKey: "", width: 0 })
                    width: spec.width
                    label: spec.label
                    sortKey: spec.sortKey
                    columnKey: spec.key
                    columnIndex: index
                    alignRight: Columns.isNumeric(spec.key)
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

    // The table is exactly as wide as the viewport: the fitted columns and the action cell are
    // laid out inside it, so there is nothing to scroll sideways (plan 133.1).
    Item {
        id: tableViewport
        objectName: "tableViewport"
        visible: !view.artwork
        anchors.top: parent.top
        anchors.topMargin: view.scrollHeading ? 0 : heading.height + columnHeader.height + 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true

        Item {
            width: tableViewport.width
            height: tableViewport.height

            ListView {
                id: list
                objectName: "trackRowsList"
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onTapped: (point, button) => {
                        if (list.indexAt(point.position.x, list.contentY + point.position.y) < 0)
                            view.workspace.clearSelection(view.groupId)
                    }
                }
                property bool navigationRestored: false
                function restoreNavigationScroll() {
                    if (navigationRestored || count === 0) return
                    const saved = view.workspace.navigationScroll(view.groupId, view.tab.id, "list")
                    const anchor = view.workspace.navigationAnchor(view.groupId, view.tab.id, "list")
                    const index = view.indexOfTrack(anchor.id)
                    if (index >= 0) {
                        positionViewAtIndex(index, ListView.Beginning)
                        contentY += anchor.offset
                    } else {
                        // Saved relative to the list header (originY is minus its height).
                        contentY = originY + saved
                    }
                    contentY = Math.min(Math.max(originY, contentHeight - height), Math.max(originY, contentY))
                    navigationRestored = true
                }
                onCountChanged: Qt.callLater(restoreNavigationScroll)
                onContentYChanged: if (navigationRestored && visible) {
                    const index = indexAt(1, contentY + 1)
                    const item = index >= 0 ? itemAtIndex(index) : null
                    const anchorId = index >= 0 && index < view.orderedIds.length ? view.orderedIds[index] : ""
                    view.workspace.setNavigationScroll(view.groupId, view.tab.id, "list",
                        contentY - originY, anchorId, item ? contentY - item.y : 0)
                }
                anchors.fill: parent
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: !view.isPlaylist
                currentIndex: -1
                highlightFollowsCurrentItem: false
                keyNavigationEnabled: false
                model: view.trackModel
                // The heading scrolls with the rows; this gap holds it and the column row.
                readonly property real scrolledY: Math.max(0, contentY - originY)
                header: Item {
                    width: list.width
                    height: view.scrollHeading ? heading.height + columnHeader.height + 8 : 0
                }
                footer: Item {
                    width: list.width; height: view.bottomInset + 28
                    Rectangle {
                        anchors.top: parent.top; width: parent.width; height: 3
                        color: Theme.primary
                        visible: view.dropIndex === view.orderedIds.length && view.trackDragActive
                    }
                    DropArea {
                        anchors.left: parent.left; anchors.right: parent.right
                        anchors.top: parent.top; height: 28
                        keys: ["mtee-playlist-entry"]
                        onEntered: drag => {
                            if (view.canReorderDrag(drag.source)) {
                                view.dropIndex = view.orderedIds.length
                                view.dropBefore = ""
                            }
                        }
                        onExited: if (view.dropIndex === view.orderedIds.length) view.dropIndex = -1
                        onDropped: drop => {
                            if (view.canReorderDrag(drop.source))
                                view.workspace.reorderPlaylistEntries(view.source, drop.source.dragEntryIds, "", drop.source.dragVersion)
                            view.dropIndex = -1
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton
                        onClicked: view.workspace.clearSelection(view.groupId)
                    }
                }
                MouseArea {
                    objectName: "emptyTrackListHitArea"
                    parent: list
                    // Below the list header (heading and column row), which must stay clickable.
                    anchors.left: list.left; anchors.right: list.right; anchors.bottom: list.bottom
                    anchors.top: list.top
                    anchors.topMargin: list.headerItem ? list.headerItem.height : 0
                    z: 10
                    enabled: list.count === 0
                    acceptedButtons: Qt.LeftButton
                    onClicked: view.workspace.clearSelection(view.groupId)
                }
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
                    groupId: view.groupId
                    separateArtist: view.modelBacked
                    selected: view.selectionIds.indexOf(modelData.id) >= 0
                    playing: view.workspace.playingId === (modelData.trackId || modelData.id)
                    paused: !view.workspace.isPlaying
                    current: view.activeFocus && list.currentIndex === index && view.selectionIds.length > 0
                    focusFrame: view.activeFocus
                    selectedAbove: index > 0 && view.selectionSet[view.orderedIds[index - 1]] === true
                    selectedBelow: index + 1 < view.orderedIds.length && view.selectionSet[view.orderedIds[index + 1]] === true
                    inPlaylist: view.workspace.playlistsContaining(modelData.trackId || modelData.id, view.workspace.revision).length > 0
                    onDragStarted: view.prepareTrackDrag(trackRow, modelData)
                    onDragMoved: (x, y) => view.moveTrackDrag(trackRow, x, y)
                    onDragFinished: view.finishTrackDrag(trackRow)
                    onMarginClicked: { view.forceActiveFocus(); view.workspace.clearSelection(view.groupId) }
                    Rectangle {
                        anchors.left: parent.left; anchors.right: parent.right
                        y: view.trackDropAfter ? parent.height - 3 : 0
                        height: 3; color: Theme.primary
                        visible: view.dropIndex === trackRow.index && view.trackDragActive
                    }
                    DropArea {
                        anchors.fill: parent
                        keys: ["mtee-playlist-entry"]
                        enabled: view.isPlaylist && view.tab.ref !== "liked"
                        onEntered: drag => {
                            if (view.canReorderDrag(drag.source)) view.setDropBoundary(trackRow.index, drag.y >= height / 2)
                        }
                        onPositionChanged: drag => {
                            if (view.canReorderDrag(drag.source)) view.setDropBoundary(trackRow.index, drag.y >= height / 2)
                        }
                        onExited: if (view.dropIndex === trackRow.index) view.dropIndex = -1
                        onDropped: drop => {
                            if (view.canReorderDrag(drop.source))
                                view.workspace.reorderPlaylistEntries(view.source, drop.source.dragEntryIds, view.dropBefore, drop.source.dragVersion)
                            view.dropIndex = -1
                        }
                    }
                    onPressed: (event) => view.press(index, event)
                    onLeftClicked: (event) => view.clickTrack(index, event)
                    onActivated: view.play(index)
                    onToggleRequested: view.workspace.togglePlay()
                    onInfoRequested: {
                        view.workspace.selectTrack(modelData.id, "single", [])
                        view.workspace.openToolWindow("info")
                    }
                    onPlaylistRequested: (anchor) => view.openPlaylistMenu(anchor, modelData.id)
                    onContextRequested: (x, y) => {
                        contextMenu.trackId = modelData.id
                        contextMenu.folderId = modelData.folder || ""
                        contextMenu.trackIds = view.selectionIds
                        contextMenu.orderedIds = view.orderedIds
                        contextMenu.captureQueueTargets()
                        contextMenu.prepare(modelData.available !== false)
                        contextMenu.popup(trackRow, x, y)
                    }
                }
            }
        }
    }

    GridView {
        id: grid
        TapHandler {
            acceptedButtons: Qt.LeftButton
            onTapped: (point, button) => {
                if (grid.indexAt(point.position.x, grid.contentY + point.position.y) < 0)
                    view.workspace.clearSelection(view.groupId)
            }
        }
        property bool navigationRestored: false
        function restoreNavigationScroll() {
            if (navigationRestored || count === 0) return
            const saved = view.workspace.navigationScroll(view.groupId, view.tab.id, "artwork")
            const anchor = view.workspace.navigationAnchor(view.groupId, view.tab.id, "artwork")
            const index = view.indexOfTrack(anchor.id)
            if (index >= 0) {
                positionViewAtIndex(index, GridView.Beginning)
                contentY += anchor.offset
            } else {
                contentY = saved
            }
            contentY = Math.min(Math.max(0, contentHeight - height), Math.max(0, contentY))
            navigationRestored = true
        }
        onCountChanged: Qt.callLater(restoreNavigationScroll)
        onContentYChanged: if (navigationRestored && visible) {
            const index = indexAt(1, contentY + 1)
            const item = index >= 0 ? itemAtIndex(index) : null
            const anchorId = index >= 0 && index < view.orderedIds.length ? view.orderedIds[index] : ""
            view.workspace.setNavigationScroll(view.groupId, view.tab.id, "artwork",
                contentY, anchorId, item ? contentY - item.y : 0)
        }
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
        reuseItems: !view.isPlaylist
        model: view.artwork ? view.trackModel : []
        footer: Item {
            width: grid.width; height: view.bottomInset + 28
            Rectangle {
                anchors.top: parent.top; width: parent.width; height: 3
                color: Theme.primary
                visible: view.dropIndex === view.orderedIds.length && view.trackDragActive
            }
            DropArea {
                anchors.left: parent.left; anchors.right: parent.right
                anchors.top: parent.top; height: 28
                keys: ["mtee-playlist-entry"]
                onEntered: drag => {
                    if (view.canReorderDrag(drag.source)) {
                        view.dropIndex = view.orderedIds.length
                        view.dropBefore = ""
                    }
                }
                onExited: if (view.dropIndex === view.orderedIds.length) view.dropIndex = -1
                onDropped: drop => {
                    if (view.canReorderDrag(drop.source))
                        view.workspace.reorderPlaylistEntries(view.source, drop.source.dragEntryIds, "", drop.source.dragVersion)
                    view.dropIndex = -1
                }
            }
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onClicked: view.workspace.clearSelection(view.groupId)
            }
        }
        MouseArea {
            parent: grid
            anchors.fill: grid
            z: 10
            enabled: grid.count === 0
            acceptedButtons: Qt.LeftButton
            onClicked: view.workspace.clearSelection(view.groupId)
        }
        ScrollBar.vertical: ThinScrollBar {}

        WheelScrollHandler {
            flickable: grid
        }

        delegate: Rectangle {
            id: tile
            objectName: "trackTile_" + (index + 1)
            required property var modelData
            required property int index
            readonly property bool selected: view.selectionIds.indexOf(modelData.id) >= 0
            readonly property bool playing: view.workspace.playingId === (modelData.trackId || modelData.id)
            property var dragTrackIds: []
            property var dragEntryIds: []
            property string dragSource: ""
            property int dragVersion: -1
            property bool dragCanAdd: false
            property int dragModifiers: 0
            property bool dragPrepared: false
            property bool dragCancelled: false
            Component.onDestruction: {
                dragCancelled = true
                if (view.trackDragSource === tile) view.cancelTrackDrag()
            }
            DragHandler {
                id: tileDrag
                target: null
                acceptedButtons: Qt.LeftButton
                enabled: tile.modelData.available !== false || !!tile.modelData.entryId
                onTranslationChanged: {
                    tile.dragModifiers = centroid.modifiers
                    if (active) view.moveTrackDrag(tile, centroid.position.x, centroid.position.y)
                }
                onActiveChanged: {
                    tile.dragModifiers = centroid.modifiers
                    if (active) {
                        tile.dragCancelled = false
                        view.prepareTrackDrag(tile, tile.modelData)
                        view.moveTrackDrag(tile, centroid.position.x, centroid.position.y)
                    } else {
                        view.finishTrackDrag(tile)
                        tile.dragPrepared = false
                    }
                }
            }

            width: grid.cellWidth
            height: grid.cellHeight
            opacity: tile.modelData.available === false ? 0.55 : 1
            color: selected ? Theme.selection : tileMouse.containsMouse ? Theme.surface : "transparent"

            Rectangle {
                x: view.trackDropAfter ? parent.width - 3 : 0
                width: 3; height: parent.height; color: Theme.primary
                visible: view.dropIndex === tile.index && view.trackDragActive
            }
            DropArea {
                anchors.fill: parent
                keys: ["mtee-playlist-entry"]
                enabled: view.isPlaylist && view.tab.ref !== "liked"
                onEntered: drag => {
                    if (view.canReorderDrag(drag.source)) view.setDropBoundary(tile.index, drag.x >= width / 2)
                }
                onPositionChanged: drag => {
                    if (view.canReorderDrag(drag.source)) view.setDropBoundary(tile.index, drag.x >= width / 2)
                }
                onExited: if (view.dropIndex === tile.index) view.dropIndex = -1
                onDropped: drop => {
                    if (view.canReorderDrag(drop.source))
                        view.workspace.reorderPlaylistEntries(view.source, drop.source.dragEntryIds, view.dropBefore, drop.source.dragVersion)
                    view.dropIndex = -1
                }
            }

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

            Row {
                z: 2
                anchors.top: parent.top; anchors.topMargin: 12
                anchors.right: parent.right; anchors.rightMargin: 12
                IconButton {
                    readonly property bool liked: view.workspace.revision >= 0 && typeof view.workspace.isLiked === "function" && view.workspace.isLiked(tile.modelData.trackId || tile.modelData.id)
                    visible: typeof view.workspace.toggleLike === "function" && tile.modelData.available !== false
                    icon: liked ? "heart-filled" : "heart"; iconSize: 16; tip: "Like track"
                    iconColor: liked ? Theme.secondary : Theme.textSecondary
                    hoverColor: liked ? Theme.secondary : Theme.textPrimary
                    onClicked: view.workspace.toggleLike(tile.modelData.trackId || tile.modelData.id)
                }
                IconButton { visible: tile.modelData.available !== false; icon: "add-playlist"; iconSize: 18; tip: "Add to playlist"; onClicked: view.openPlaylistMenu(this, tile.modelData.id) }
                TextButton { visible: tile.modelData.available === false && view.isPlaylist && !view.isPluginList; text: "Locate"; onClicked: view.workspace.playlistModel.requestUI("locate", tile.modelData.entryId, [tile.modelData.id]) }
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
                        contextMenu.trackIds = view.selectionIds
                        contextMenu.orderedIds = view.orderedIds
                        contextMenu.captureQueueTargets()
                        contextMenu.prepare(tile.modelData.available !== false)
                        contextMenu.popup(tile, event.x, event.y)
                    }
                }
            }
        }
    }

    TrackMenu {
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
        // Position among the drawn columns: the border after the last one has no handle.
        property int columnIndex: -1
        readonly property bool sorted: view.tab.sortMode === "manual"
            && view.tab.sortKey === sortKey && sortKey.length > 0

        height: parent.height

        // The header being dragged: a copy follows the pointer over the other headers, which
        // hold the drop areas. The cell itself stays in its row until the drop.
        Rectangle {
            id: dragGhost
            property string columnKey: cell.columnKey
            // Hidden by opacity, not visibility: hiding the source ends the drag before its drop.
            opacity: columnDragHandler.active ? 0.92 : 0
            z: 10
            width: cell.width
            height: cell.height
            x: columnDragHandler.active ? columnDragHandler.centroid.position.x - width / 2 : 0
            color: Theme.surface
            border.width: 1
            border.color: Theme.primary
            Drag.active: columnDragHandler.active
            Drag.source: dragGhost
            Drag.keys: ["mtee-column"]
            Drag.supportedActions: Qt.MoveAction
            Drag.hotSpot.x: width / 2
            Drag.hotSpot.y: height / 2

            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 6
                text: cell.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

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
                else if (cell.sortKey.length > 0) {
                    view.workspace.focusGroup(view.groupId)
                    view.workspace.setSort(view.tab.id, cell.sortKey)
                }
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
                    // Releasing the pointer must drop explicitly; ending the drag only cancels it.
                    dragGhost.Drag.drop()
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

        // Guide line on the border between this column and the next: shown while the handle is
        // hovered or dragged.
        Rectangle {
            id: resizeGuide
            visible: resizeHandle.visible && (resizeHandle.containsMouse || resizeHandle.pressed)
            z: 3
            width: 2
            x: cell.width + view.columns.gap / 2 - width / 2
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            color: resizeHandle.pressed ? Theme.primary : Theme.separator
        }

        // The grab zone: 8 px centred on the border, one handle per border between two drawn
        // columns, none after the last one. A drag moves the border: columns.js resizeBoundary
        // decides the widths, so the table keeps its width (plan 133.3).
        MouseArea {
            id: resizeHandle
            objectName: "columnResizeHandle_" + cell.columnKey
            visible: view.modelBacked && cell.columnKey.length > 0
                && cell.columnIndex >= 0 && cell.columnIndex < view.columns.items.length - 1
            z: 3
            width: 8
            x: cell.width + view.columns.gap / 2 - width / 2
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.SizeHorCursor
            // Keeps the column reorder DragHandler from taking the press while a resize is active.
            preventStealing: true
            property real startX: 0
            // The widths drawn at the press: every drag step is computed from them.
            property var baseItems: []
            property bool moved: false

            // Pointer x in the list, not in this handle: the handle moves as the border moves.
            function viewX(mouse) {
                return resizeHandle.mapToItem(view, mouse.x, 0).x
            }

            onPressed: (mouse) => {
                startX = viewX(mouse)
                moved = false
                baseItems = view.columns.items.map(item => ({ key: item.key, width: item.width }))
            }
            onPositionChanged: (mouse) => {
                if (!pressed)
                    return
                const delta = Math.round(viewX(mouse) - startX)
                if (delta !== 0)
                    moved = true
                const next = ({})
                for (const item of Columns.resizeBoundary(baseItems, cell.columnIndex, delta, view.columns.room))
                    next[item.key] = Math.round(item.width)
                view.localColumnWidths = next
            }
            // Only a real drag writes widths, and only the columns whose width changed.
            onReleased: {
                if (moved) {
                    const changed = ({})
                    const widths = view.localColumnWidths
                    for (const item of baseItems) {
                        const width = Number(widths[item.key] || 0)
                        if (width > 0 && width !== Math.round(item.width))
                            changed[item.key] = width
                    }
                    if (Object.keys(changed).length > 0)
                        view.workspace.resizeColumns(view.tab.id, changed)
                }
                moved = false
                view.localColumnWidths = ({})
            }
            onCanceled: {
                moved = false
                view.localColumnWidths = ({})
            }
            // A double-click puts this column back to its default width (Title back to automatic).
            onDoubleClicked: {
                const widths = ({})
                widths[cell.columnKey] = Number(view.columns.defaults[cell.columnKey] || 0)
                view.workspace.resizeColumns(view.tab.id, widths)
                moved = false
                view.localColumnWidths = ({})
            }
        }
    }
}
