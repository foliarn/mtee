import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The one right-click menu of a track (plan 130, P6), on top of ActionMenu. Groups, in order:
//   queue and playlists | Go to artist, Show in folder | Analyze, Edit info, Convert |
//   the groups of plugins (TrackAction) | Open in Windows Explorer, Rename file, Delete file.
// ``source`` is the list the track sits in ("folder:...", "playlist:...", a plugin list), used by
// the plugin actions and to remove from a playlist. ``listKind`` is "list" (a folder, playlist
// or plugin list), "explorer" (the tree), "queue", "history" or "playing" (the Fullscreen menu).
// A row without a local file offers only what works without one. ``extraGroups`` come first
// (the Queue puts "Remove from queue" there).
ActionMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property var orderedIds: []
    property var queueTargets: []
    property string queueSource: ""
    property string trackId: ""
    property string source: ""
    property string folderId: ""
    property string listKind: "list"
    // A row without a local file hides the actions that need one.
    property bool rowAvailable: true
    property bool showAddToQueue: true
    // The Fullscreen player opens the playlist chooser itself.
    property bool externalPlaylistChooser: false
    property var extraGroups: []
    // The captioned groups of the plugins for the selected rows: {header, label, key}.
    property var pluginItems: []
    property var artists: []
    signal addToPlaylistRequested()

    readonly property bool inPlaylist: source.indexOf("playlist:") === 0 && listKind === "list"
    readonly property bool hasMapping: typeof workspace.localTrackIds === "function"

    // The library ids behind the rows: a plugin row maps to its local track, if it has one.
    function localIds(ids) {
        return listKind === "list" && hasMapping ? workspace.localTrackIds(ids) : ids
    }

    function localId() {
        return localIds([trackId])[0] || ""
    }

    // The selection when the clicked track is part of it, else the clicked track.
    function targetIds() {
        return trackIds.indexOf(trackId) >= 0 ? trackIds : [trackId]
    }

    function captureQueueTargets() {
        const selected = targetIds()
        queueTargets = orderedIds.filter(identity => selected.indexOf(identity) >= 0)
        if (queueTargets.length === 0)
            queueTargets = [trackId]
        queueSource = source
    }

    function pluginGroups() {
        const result = []
        let current = null
        for (const entry of pluginItems) {
            if (entry.header || current === null) {
                current = { "id": "plugin:" + entry.label, "items": [] }
                result.push(current)
            }
            current.items.push({
                "id": "plugin:" + entry.key,
                "label": entry.header ? entry.label.toUpperCase() : entry.label,
                "enabled": !entry.header,
                "objectName": "pluginAction_" + entry.key
            })
        }
        return result
    }

    function buildGroups() {
        const available = rowAvailable
        const local = available ? localId() : ""
        const withFile = available && local.length > 0
        const artistItems = artists.length === 1
            ? [{ "id": "artist:" + artists[0].id, "label": "Go to artist" }]
            : artists.length > 1
                ? [{ "id": "artists", "label": "Go to artist",
                     "submenu": artists.map(artist => ({ "id": "artist:" + artist.id, "label": artist.name })) }]
                : []
        const hideFolder = listKind === "explorer" || (listKind === "list" && source.indexOf("folder:") === 0)
        const groups = []
        for (const group of extraGroups)
            groups.push(group)
        groups.push({ "id": "queue", "items": [
            { "id": "addToQueue", "label": "Add to queue", "objectName": "addToQueueAction",
              "visible": available && showAddToQueue },
            { "id": "addToPlaylist", "label": "Add to playlist…", "objectName": "addToPlaylistAction",
              "visible": available },
            { "id": "removeFromPlaylist", "label": "Remove from this playlist",
              "objectName": "removeFromPlaylistAction", "visible": inPlaylist
                && typeof workspace.playlistModel !== "undefined" }
        ] })
        groups.push({ "id": "go", "items": artistItems.concat([
            { "id": "showInFolder", "label": "Show in folder", "visible": available && !hideFolder }
        ]) })
        groups.push({ "id": "tools", "items": [
            { "id": "analyze", "label": "Analyze", "objectName": "analyzeAction", "visible": available },
            { "id": "editInfo", "label": "Edit info", "hint": "Ctrl+I", "visible": available },
            { "id": "convert", "label": "Convert…", "visible": workspace.pluginUiEnabled === true }
        ] })
        for (const group of pluginGroups())
            groups.push(group)
        groups.push({ "id": "file", "items": [
            { "id": "openInExplorer", "label": "Open in Windows Explorer", "visible": withFile },
            { "id": "renameFile", "label": "Rename file…", "visible": withFile,
              "enabled": targetIds().length === 1 && typeof workspace.requestRenameFile === "function" },
            { "id": "deleteFile", "label": "Delete file…", "hint": "Del", "danger": true,
              "visible": withFile, "enabled": typeof workspace.trashModel !== "undefined" }
        ] })
        return groups
    }

    // Called before the menu opens, once the selection is set: the row decides what is offered.
    function prepare(available) {
        rowAvailable = available
        pluginItems = typeof workspace.pluginTrackActions === "function"
            ? workspace.pluginTrackActions(source, targetIds()) : []
        const credited = typeof workspace.trackArtists === "function"
            ? workspace.trackArtists(listKind === "list" ? localId() : trackId) : []
        artists = credited || []
        groups = buildGroups()
    }

    onTriggered: (actionId) => {
        const targets = targetIds()
        if (actionId === "addToQueue") {
            workspace.enqueueTracks(queueTargets, queueSource, [])
        } else if (actionId === "addToPlaylist") {
            if (externalPlaylistChooser)
                addToPlaylistRequested()
            else
                playlistPopup.popup(menu.parent, menu.x, menu.y)
        } else if (actionId === "removeFromPlaylist") {
            workspace.playlistModel.remove(source.split(":")[1], targets)
        } else if (actionId.indexOf("artist:") === 0) {
            const key = actionId.substring(7)
            const found = artists.find(artist => artist.id === key)
            workspace.openArtistPage(key, found ? found.name : "")
        } else if (actionId === "showInFolder") {
            workspace.revealTrack(listKind === "list" ? localId() || trackId : trackId, source)
        } else if (actionId === "analyze") {
            workspace.analyzeTracks(localIds(targets), false)
        } else if (actionId === "editInfo") {
            if (listKind === "list" || listKind === "explorer")
                workspace.showRightPanel("info")
            else
                workspace.revealTrackForEdit(trackId, source)
        } else if (actionId === "convert") {
            if (listKind === "list") {
                workspace.addSelectionToConvert()
                workspace.openConvert()
            } else {
                workspace.addTracksToConvert(targets)
            }
        } else if (actionId.indexOf("plugin:") === 0) {
            workspace.runPluginTrackAction(source, targets, actionId.substring(7))
        } else if (actionId === "openInExplorer") {
            workspace.showInExplorer(localId())
        } else if (actionId === "renameFile") {
            workspace.requestRenameFile(localId())
        } else if (actionId === "deleteFile") {
            workspace.trashModel.request_recycle(localIds(targets))
        }
    }

    AddToPlaylistMenu {
        id: playlistPopup
        workspace: menu.workspace
        trackIds: menu.targetIds()
    }
}
