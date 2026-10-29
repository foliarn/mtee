import QtQuick
import QtQuick.Controls.Basic
import Mtee

AppMenu {
    id: menu

    required property var workspace
    property var trackIds: []
    property var orderedIds: []
    property var queueTargets: []
    property string queueSource: ""
    property string trackId: ""
    property string source: ""
    property string folderId: ""
    // A row without a local file hides the actions that need one (the file, the queue, the tags).
    property bool rowAvailable: true
    // The captioned groups of the plugins for the selected rows: {header, label, key}.
    property var pluginItems: []

    AppMenuItem {
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
        text: "Play"
        hint: "Enter"
        onTriggered: menu.workspace.playTrack(menu.trackId, menu.source)
    }
    AppMenuItem {
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
        objectName: "addToQueueAction"
        text: "Add to queue"
        onTriggered: menu.workspace.enqueueTracks(menu.queueTargets, menu.queueSource, [])
    }

    AppMenuItem {
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
        text: "Edit info"
        hint: "Ctrl+I"
        onTriggered: menu.workspace.showRightPanel("info")
    }

    AppMenuItem {
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
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

    AppMenuSeparator { visible: menu.rowAvailable; height: visible ? implicitHeight : 0 }

    AppMenuItem {
        visible: menu.workspace.pluginUiEnabled
        text: "Convert…"
        onTriggered: {
            menu.workspace.addSelectionToConvert()
            menu.workspace.openConvert()
        }
    }

    AppMenuItem {
        objectName: "analyzeAction"
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
        text: "Analyze"
        onTriggered: menu.workspace.analyzeTracks(typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds(menu.targetIds()) : menu.targetIds(), false)
    }

    AppMenuItem {
        visible: menu.rowAvailable
        height: visible ? implicitHeight : 0
        text: "Show in Explorer"
        onTriggered: menu.workspace.showInExplorer(typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds([menu.trackId])[0] || "" : menu.trackId)
    }

    AppMenuSeparator { visible: menu.rowAvailable; height: visible ? implicitHeight : 0 }

    // The actions of plugins, one captioned group each, flat, before the file actions.
    Instantiator {
        model: menu.pluginItems
        delegate: AppMenuItem {
            required property var modelData
            text: modelData.header ? modelData.label.toUpperCase() : modelData.label
            enabled: !modelData.header
            onTriggered: menu.workspace.runPluginTrackAction(menu.source, menu.targetIds(), modelData.key)
        }
        // Each entry goes right before the separator that precedes File actions.
        onObjectAdded: (index, object) => menu.insertItem(menu.separatorIndex(), object)
        onObjectRemoved: (index, object) => menu.removeItem(object)
    }

    AppMenuSeparator {
        id: fileSeparator
        visible: menu.rowAvailable && menu.pluginItems.length > 0
        height: visible ? implicitHeight : 0
    }

    FileActionsMenu {
        id: fileActions
        workspace: menu.workspace
        trackIds: typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds(menu.trackIds) : menu.trackIds
        trackId: typeof menu.workspace.localTrackIds === "function" ? menu.workspace.localTrackIds([menu.trackId])[0] || "" : menu.trackId
    }

    function separatorIndex() {
        for (let i = 0; i < count; ++i) {
            if (itemAt(i) === fileSeparator)
                return i
        }
        return count
    }

    // Called before the menu opens, once the selection is set: the row decides what is offered.
    function prepare(available) {
        rowAvailable = available
        pluginItems = typeof workspace.pluginTrackActions === "function"
            ? workspace.pluginTrackActions(source, targetIds()) : []
        // The File actions entry is a sub menu: hide the item that opens it.
        for (let i = 0; i < count; ++i) {
            const item = itemAt(i)
            if (item && item.subMenu === fileActions) {
                item.visible = available
                item.height = available ? item.implicitHeight : 0
            }
        }
    }

    // The selection when the clicked track is part of it, else the clicked track.
    function targetIds() {
        return trackIds.indexOf(trackId) >= 0 ? trackIds : [trackId]
    }

    function captureQueueTargets() {
        const selected = targetIds()
        queueTargets = orderedIds.filter(identity => selected.indexOf(identity) >= 0)
        if (queueTargets.length === 0) queueTargets = [trackId]
        queueSource = source
    }
}
