import QtQuick
import Mtee

// One dock of the frame (plan 131.6): the tool windows of one side, one or two rounded windows
// stacked vertically with a split between them (ratio saved), and a handle on the inner edge that
// resizes the dock (width saved). The panes are chosen by tool window id in ``DockWindow``. A window
// whose pane draws its own PaneHeader keeps it (title and actions); the others get a PaneHeader
// with the title and a close button. The dock is hidden when closed, empty or in fullscreen.
Item {
    id: dock

    required property var workspace
    // "left" or "right": the side of the workspace state this dock shows.
    required property string side

    // Bumped on every layout change, so the state is read again.
    property int revision: 0
    readonly property var info: { dock.revision; return dock.workspace.dockState(dock.side) }
    readonly property var windowIds: info.windows ? info.windows : []
    readonly property bool shown: info.open === true && windowIds.length > 0 && !workspace.fullscreen
    readonly property bool stacked: windowIds.length > 1
    readonly property int gap: Theme.windowGap
    readonly property real firstHeight: stacked ? Math.round((height - gap) * (info.ratio || 0.5)) : height
    readonly property var entries: workspace.toolWindows ? workspace.toolWindows.entries : []
    // The value at the press of a handle drag; the handle reports the distance from that press.
    property real dragStartValue: 0
    // Below the overlay width the dock floats over the centre: it is elevated and its width keeps
    // at least 160 px of the body free (never under its minimum width).
    property bool floating: false
    property real bodyWidth: 0

    width: info.width ? Math.min(info.width, Math.max(Theme.leftDockMin, bodyWidth - 160)) : 0
    visible: shown

    // The elevation of a floating dock: two soft translucent layers behind its windows.
    Rectangle {
        objectName: "dockShadowOuter"
        visible: dock.floating && dock.shown
        x: -6
        y: -1
        width: dock.width + 12
        height: dock.height + 8
        z: -2
        radius: Theme.radiusWindow + 6
        color: "#14000000"
    }

    Rectangle {
        objectName: "dockShadowInner"
        visible: dock.floating && dock.shown
        x: -3
        y: 2
        width: dock.width + 6
        height: dock.height + 4
        z: -1
        radius: Theme.radiusWindow + 3
        color: "#1F000000"
    }

    Connections {
        target: dock.workspace
        function onLayoutChanged() { dock.revision++ }
    }

    // The windows whose panes draw their own header; the others get the dock's PaneHeader.
    function hasOwnHeader(windowId) {
        return windowId !== "info" && windowId !== "queue" && windowId !== "history"
            && windowId !== "convert"
    }

    function titleOf(windowId) {
        for (let i = 0; i < entries.length; ++i) {
            if (entries[i].id === windowId)
                return entries[i].title
        }
        return windowId
    }

    // One rounded window of the dock: its header (when the pane has none) and its pane.
    component DockWindow: WindowSurface {
        id: win

        required property string windowId
        readonly property bool ownHeader: dock.hasOwnHeader(windowId)

        Component { id: explorerPane; ExplorerPane { workspace: dock.workspace } }
        Component { id: playlistsPane; PlaylistsPane { workspace: dock.workspace } }
        Component { id: artistsPane; ArtistsPane { workspace: dock.workspace } }
        Component {
            id: artistsUnavailablePane
            PlaceholderPane {
                title: "Artists"
                icon: "artists"
                message: "Artists are not available in this demo."
            }
        }
        Component { id: pluginsViewPane; PluginsViewPane { workspace: dock.workspace } }
        Component { id: tasksPane; TasksPane { workspace: dock.workspace } }
        // The Convert pane belongs to the conversion plugin: it is loaded only when that window is
        // shown, which the workspace allows only when the plugin is enabled.
        Component {
            id: convertPane
            Loader {
                anchors.fill: parent
                Component.onCompleted: setSource("ConvertPane.qml", { "workspace": dock.workspace })
            }
        }
        // A pane of a plugin window, drawn from its contributions.
        Component { id: pluginPane; PluginPane { workspace: dock.workspace; activity: win.windowId } }
        Component { id: infoPane; InfoPanel { workspace: dock.workspace } }
        Component { id: queuePane; QueuePanel { workspace: dock.workspace; bottomInset: 0 } }
        Component { id: historyPane; HistoryPanel { workspace: dock.workspace; bottomInset: 0 } }

        PaneHeader {
            id: strip
            visible: !win.ownHeader
            width: parent.width
            title: dock.titleOf(win.windowId)

            IconButton {
                objectName: "dockClose_" + win.windowId
                icon: "close"
                iconSize: 16
                width: 26
                height: 26
                tip: "Close"
                onClicked: dock.workspace.closeToolWindow(win.windowId)
            }
        }

        Loader {
            anchors.top: win.ownHeader ? parent.top : strip.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            sourceComponent: {
                const id = win.windowId
                if (id === "explorer") return explorerPane
                if (id === "playlists") return playlistsPane
                if (id === "artists") return dock.workspace.artistList ? artistsPane : artistsUnavailablePane
                if (id === "plugins") return pluginsViewPane
                if (id === "tasks") return tasksPane
                if (id === "convert") return convertPane
                if (id === "info") return infoPane
                if (id === "queue") return queuePane
                if (id === "history") return historyPane
                if (id.indexOf(".") > 0) return pluginPane
                return null
            }
        }
    }

    DockWindow {
        id: first
        objectName: "dockFirst"
        visible: dock.windowIds.length > 0
        windowId: dock.windowIds.length > 0 ? dock.windowIds[0] : ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: dock.firstHeight
    }

    DockWindow {
        id: second
        objectName: "dockSecond"
        visible: dock.stacked
        windowId: dock.stacked ? dock.windowIds[1] : ""
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.max(0, dock.height - dock.firstHeight - dock.gap)
    }

    // The split between two stacked windows: drag it to share the height (ratio saved).
    SplitHandle {
        objectName: "dockSplit"
        orientation: Qt.Vertical
        visible: dock.stacked
        width: dock.width
        x: 0
        y: dock.firstHeight + dock.gap / 2 - height / 2
        onDragStarted: dock.dragStartValue = dock.info.ratio
        onDragged: (delta) => dock.workspace.setDockRatio(
            dock.side, dock.dragStartValue + delta / Math.max(1, dock.height - dock.gap))
    }

    // The handle on the inner edge, in the gap to the centre: drag it to resize the dock.
    SplitHandle {
        objectName: "dockResize"
        orientation: Qt.Horizontal
        visible: dock.shown
        height: dock.height
        x: dock.side === "left" ? dock.width + dock.gap / 2 - width / 2 : -dock.gap / 2 - width / 2
        onDragStarted: dock.dragStartValue = dock.width
        onDragged: (delta) => dock.workspace.setDockWidth(
            dock.side, Math.round(dock.dragStartValue + (dock.side === "left" ? delta : -delta)))
    }
}
