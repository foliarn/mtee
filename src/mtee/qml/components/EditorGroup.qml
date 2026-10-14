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

    Rectangle {
        id: strip
        width: parent.width
        height: Theme.tabHeight
        color: Theme.sidebar

        ListView {
            id: tabs
            anchors.left: parent.left
            anchors.right: actions.left
            height: parent.height
            orientation: ListView.Horizontal
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            model: group.groupData.tabs
            MouseArea {
                parent: tabs
                x: Math.min(tabs.width, Math.max(0, tabs.contentWidth - tabs.contentX))
                width: Math.max(0, tabs.width - x)
                height: tabs.height
                z: 10
                acceptedButtons: Qt.LeftButton
                onClicked: group.workspace.clearSelection(group.groupIndex)
            }

            delegate: Rectangle {
                id: tab

                required property var modelData
                readonly property bool isActive: modelData.id === group.groupData.active

                width: Math.min(220, tabRow.implicitWidth + 44)
                height: Theme.tabHeight
                color: isActive ? Theme.editor : tabMouse.containsMouse ? Theme.chrome : "transparent"

                Rectangle {
                    visible: tab.isActive
                    width: parent.width
                    height: 1
                    color: group.focused ? Theme.primary : Theme.textMuted
                }

                Rectangle {
                    anchors.right: parent.right
                    width: 1
                    height: parent.height
                    color: Theme.chrome
                }

                MouseArea {
                    id: tabMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                    onClicked: (event) => {
                        if (event.button === Qt.MiddleButton)
                            group.workspace.closeTab(group.groupIndex, tab.modelData.id)
                        else
                            group.workspace.activateTab(group.groupIndex, tab.modelData.id)
                    }
                    onDoubleClicked: (event) => {
                        if (event.button === Qt.LeftButton && tab.modelData.preview
                                && typeof group.workspace.keepTab === "function")
                            group.workspace.keepTab(group.groupIndex, tab.modelData.id)
                    }
                }

                Row {
                    id: tabRow
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: tab.modelData.kind === "folder" ? "folder"
                            : tab.modelData.kind === "playlist" ? "playlists"
                            : tab.modelData.kind === "convert" ? "convert"
                            : tab.modelData.kind === "tasks" ? "tasks"
                            : tab.modelData.kind === "artists" || tab.modelData.kind === "artist" ? "artists"
                            : tab.modelData.kind === "genre_manager" ? "plugins"
                            : tab.modelData.kind === "profile" ? "profile"
                            : "settings"
                        size: 15
                        color: tab.isActive ? Theme.primary : Theme.textMuted
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(implicitWidth, 150)
                        text: tab.modelData.title
                        font.italic: tab.modelData.preview === true
                        elide: Text.ElideRight
                        color: tab.isActive ? Theme.textPrimary : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }

                IconButton {
                    anchors.right: parent.right
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    width: 20
                    height: 20
                    visible: tab.isActive || tabMouse.containsMouse || hovered
                    icon: "close"
                    iconSize: 14
                    tip: "Close"
                    onClicked: group.workspace.closeTab(group.groupIndex, tab.modelData.id)
                }
            }
        }

        Row {
            id: actions
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Repeater {
                model: group.singleGroup && group.groupCount > 1 ? group.groupCount : 0
                delegate: TextButton {
                    required property int index
                    implicitHeight: 24
                    kind: index === group.workspace.activeGroup ? "neutral" : "ghost"
                    text: "Group " + (index + 1)
                    onClicked: group.workspace.setActiveGroup(index)
                }
            }

            IconButton {
                width: 28
                height: 28
                icon: "split"
                iconSize: 16
                active: group.groupCount > 1
                tip: group.groupCount > 1 ? "Join editor groups (Ctrl+\\)" : "Split editor (Ctrl+\\)"
                onClicked: group.workspace.toggleSplit()
            }

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
        }
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
            : group.activeTab.kind === "artists" ? (group.activeTab.id === "artists:catalog" ? artistCatalogComponent : artistReviewComponent)
            : group.activeTab.kind === "genre_manager" ? genreManagerComponent
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

    Component {
        id: convertComponent
        ConvertView {
            workspace: group.workspace
            bottomInset: group.bottomInset
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
        id: artistReviewComponent
        ArtistReviewView {
            workspace: group.workspace
            tab: group.activeTab
            bottomInset: group.bottomInset
        }
    }

    Component {
        id: genreManagerComponent
        GenreManagerView {
            workspace: group.workspace
            tab: group.activeTab
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
