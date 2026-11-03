import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../views"

// Tab strip and content of one editor group, as in VS Code: the active tab of
// the focused group carries a primary line on top.
Rectangle {
    id: group

    required property var workspace
    property int groupIndex: 0
    property var groupData: ({ "tabs": [], "active": "" })
    property int groupCount: 1
    property bool singleGroup: false
    property int bottomInset: 0
    readonly property bool focused: workspace.activeGroup === groupIndex
    readonly property var activeTab: {
        for (const tab of groupData.tabs)
            if (tab.id === groupData.active)
                return tab
        return null
    }

    objectName: "editorGroup" + groupIndex
    color: Theme.editor

    function selectAll() {
        if (content.item && content.item.selectAll)
            content.item.selectAll()
    }

    TabStrip {
        id: strip
        width: parent.width
        groupId: group.groupIndex
        tabs: group.groupData.tabs
        activeId: group.groupData.active
        focused: group.focused
        onTabClicked: (tabId) => group.workspace.activateTab(group.groupIndex, tabId)
        onTabClosed: (tabId) => group.workspace.closeTab(group.groupIndex, tabId)
        onTabKept: (tabId) => {
            if (typeof group.workspace.keepTab === "function")
                group.workspace.keepTab(group.groupIndex, tabId)
        }
        onEmptyClicked: group.workspace.clearSelection(group.groupIndex)

        trailing: [
            Repeater {
                model: group.singleGroup && group.groupCount > 1 ? group.groupCount : 0
                delegate: TextButton {
                    required property int index
                    implicitHeight: 24
                    kind: index === group.workspace.activeGroup ? "neutral" : "ghost"
                    text: "Group " + (index + 1)
                    onClicked: group.workspace.setActiveGroup(index)
                }
            },

            IconButton {
                width: 28
                height: 28
                icon: "split"
                iconSize: 16
                active: group.groupCount > 1
                tip: group.groupCount > 1 ? "Join editor groups (Ctrl+\\)" : "Split editor (Ctrl+\\)"
                onClicked: group.workspace.toggleSplit()
            },

            IconButton {
                objectName: "toggleRightPanel"
                visible: group.groupIndex === group.groupCount - 1
                width: 28
                height: 28
                icon: "panel-right"
                iconSize: 16
                active: group.workspace.rightPanelVisible
                tip: group.workspace.rightPanelVisible ? "Hide side panel" : "Show side panel"
                onClicked: group.workspace.toggleRightPanel(group.workspace.rightPanelTab)
            }
        ]
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

    Component {
        id: listComponent
        TrackListView {
            workspace: group.workspace
            tab: group.activeTab
            groupIndex: group.groupIndex
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
            // The page follows the tab that is active in this group.
            onLoaded: item.tab = Qt.binding(() => group.activeTab)
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
            groupIndex: group.groupIndex
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
                onClicked: group.workspace.clearSelection(group.groupIndex)
            }
        }
    }

    Rectangle {
        visible: group.groupIndex > 0 && !group.singleGroup
        width: 1
        height: parent.height
        color: Theme.separator
    }
}
