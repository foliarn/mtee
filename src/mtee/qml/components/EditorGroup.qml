import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../views"

// One centre window (plan 131.7): a rounded WindowSurface with its tab strip and content, as in VS
// Code. The focused window's tab strip shows it; a click anywhere inside focuses it, and the
// press still reaches the content. Tabs reorder and move between windows on their strip. A tab or an
// Explorer folder dropped on an edge of the window splits it (P3); a drop in the middle adds the tab.
WindowSurface {
    id: group

    required property var workspace
    property string groupId: ""
    property int groupIndex: 0
    property var groupData: ({ "tabs": [], "active": "" })
    property int groupCount: 1
    property bool singleGroup: false
    property int bottomInset: 0
    // The focused window is told by its tab strip only; the surface draws no outline.
    readonly property bool isActiveWindow: workspace.activeGroup === groupId
    readonly property var activeTab: {
        for (const tab of groupData.tabs)
            if (tab.id === groupData.active)
                return tab
        return null
    }
    // The zones this window offers: a split must leave both windows above their minimum size.
    readonly property var allowedZones: {
        const zones = ["center"]
        if (group.width >= 2 * Theme.minCenterWindowWidth + Theme.windowGap)
            zones.push("left", "right")
        if (group.height >= 2 * Theme.minCenterWindowHeight + Theme.windowGap)
            zones.push("top", "bottom")
        return zones
    }

    objectName: "editorGroup" + groupIndex
    color: Theme.editor

    function selectAll() {
        if (content.item && content.item.selectAll)
            content.item.selectAll()
    }

    // A tab or a folder dropped on this window: an edge splits it, the middle takes the tab.
    function dropOn(zone, payload) {
        if (!payload)
            return
        if (payload.type === "folder") {
            group.workspace.openFolderAt(String(payload.folderId), group.groupId, zone)
            return
        }
        if (payload.type !== "tab")
            return
        if (zone === "center") {
            if (payload.groupId !== group.groupId)
                group.workspace.moveTab(payload.groupId, payload.tabId, group.groupId,
                    group.groupData.tabs.length)
            return
        }
        group.workspace.splitWithTab(group.groupId, zone, payload.groupId, payload.tabId)
    }

    // Below the single-window width only the focused window is drawn: this strip's switcher lists the
    // other windows, each by the title of its active tab (plan 131.9).
    readonly property bool switcherOffered: singleGroup && groupCount > 1
    readonly property var otherWindows: {
        const entries = []
        for (const other of workspace.groups) {
            if (other.id === groupId)
                continue
            const active = other.tabs.find(tab => tab.id === other.active)
            entries.push({ "id": other.id, "title": active ? active.title : "Empty window" })
        }
        return entries
    }

    TabStrip {
        id: strip
        width: parent.width
        groupId: group.groupId
        tabs: group.groupData.tabs
        activeId: group.groupData.active
        focused: group.isActiveWindow
        switcher: group.switcherOffered
        switcherEntries: group.otherWindows
        onSwitcherChosen: (windowId) => group.workspace.focusGroup(windowId)
        onTabClicked: (tabId) => group.workspace.activateTab(group.groupId, tabId)
        onTabClosed: (tabId) => group.workspace.closeTab(group.groupId, tabId)
        onTabKept: (tabId) => {
            if (typeof group.workspace.keepTab === "function")
                group.workspace.keepTab(group.groupId, tabId)
        }
        onEmptyClicked: group.workspace.clearSelection(group.groupId)
        onTabMoved: (tabId, toIndex) => group.workspace.moveTab(group.groupId, tabId, group.groupId, toIndex)
        onTabDropped: (payload, toIndex) => group.workspace.moveTab(payload.groupId, payload.tabId,
            group.groupId, toIndex)
    }

    Loader {
        id: content
        anchors.top: strip.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        sourceComponent: group.activeTab === null ? emptyComponent
            : group.activeTab.kind === "convert" ? convertComponent
            : group.activeTab.kind === "settings" ? settingsComponent
            : group.activeTab.kind === "profile" ? profileComponent
            : group.activeTab.kind === "tasks" ? tasksComponent
            : group.activeTab.kind === "artists" ? artistCatalogComponent
            : group.activeTab.kind === "plugin" ? pluginDetailComponent
            : group.workspace.pluginUi && group.workspace.pluginUi.tabQml(group.activeTab.kind).length > 0 ? pluginTabComponent
            : listComponent
    }

    // Drop zones over the content: they show while a tab or a folder is dragged over the window.
    DropZoneOverlay {
        id: zones
        objectName: "windowDropZones"
        anchors.top: strip.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        allowed: group.allowedZones
        onDropped: (zone, payload) => group.dropOn(zone, payload)
    }

    Component {
        id: listComponent
        TrackListView {
            workspace: group.workspace
            tab: group.activeTab
            groupId: group.groupId
            bottomInset: group.bottomInset
        }
    }

    // The detail tab of a plugin in the Plugins view (tab kind "plugin", ref = plugin id).
    Component {
        id: pluginDetailComponent
        PluginDetailPane {
            workspace: group.workspace
            tab: group.activeTab
            groupIndex: group.groupIndex
            bottomInset: group.bottomInset
        }
    }

    // The Convert view belongs to the conversion plugin: it is loaded only for a Convert tab,
    // which the workspace opens only when the plugin is enabled.
    Component {
        id: convertComponent
        Loader {
            anchors.fill: parent
            Component.onCompleted: setSource("../views/ConvertView.qml", {
                "workspace": group.workspace,
                "bottomInset": group.bottomInset
            })
        }
    }

    // A tab of a plugin whose content is a QML file of the plugin. The public tree names no
    // plugin type: the file is loaded by URL and gets the workspace and the plugin's backend.
    Component {
        id: pluginTabComponent
        Loader {
            anchors.fill: parent
            readonly property string kind: group.activeTab ? group.activeTab.kind : ""
            function load() {
                setSource(group.workspace.pluginUi.tabQml(kind), {
                    "workspace": group.workspace,
                    "groupIndex": group.groupIndex,
                    "bottomInset": group.bottomInset,
                    "backend": group.workspace.pluginUi.tabBackend(kind)
                })
            }
            Component.onCompleted: load()
            onKindChanged: load()
            // The page follows the tab that is active in this group. The window id is set after the
            // load, so a page that does not declare it gets no warning about an unknown property.
            onLoaded: {
                item.tab = Qt.binding(() => group.activeTab)
                item.groupId = group.groupId
            }
        }
    }

    Component {
        id: tasksComponent
        TasksView {
            workspace: group.workspace
            bottomInset: group.bottomInset
        }
    }

    Component {
        id: artistCatalogComponent
        ArtistsView {
            workspace: group.workspace
            bottomInset: group.bottomInset
        }
    }

    Component {
        id: settingsComponent
        SettingsView {
            workspace: group.workspace
            groupId: group.groupId
            bottomInset: group.bottomInset
        }
    }

    Component {
        id: profileComponent
        ProfileView {
            workspace: group.workspace
            bottomInset: group.bottomInset
        }
    }

    Component {
        id: emptyComponent
        EmptyEditor {
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton
                onClicked: group.workspace.clearSelection(group.groupId)
            }
        }
    }

    // Any click inside the window focuses it. The press is passed on, so the content still gets it.
    MouseArea {
        objectName: "windowFocusArea"
        anchors.fill: parent
        z: 500
        acceptedButtons: Qt.LeftButton
        propagateComposedEvents: true
        onPressed: (mouse) => {
            group.workspace.focusGroup(group.groupId)
            mouse.accepted = false
        }
    }
}
