import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window

// The tab strip of a center window (plan 130), extracted from EditorGroup. A tab is
// {id, title, kind, icon, preview}. The active tab of a ``focused`` strip carries the accent line,
// the tabs of the other strips are muted (P11). Dragging a tab starts a drag with the payload
// {type: "tab", groupId, tabId} (``Drag.keys`` "mtee-tab"); dropping on another tab of the same
// strip emits ``tabMoved``, dropping elsewhere is handled by the window that receives it. When
// the tabs do not fit, a drop-down lists them all. In ``switcher`` mode a drop-down lists the
// other windows (``switcherEntries`` of {id, title}) and emits ``switcherChosen``.
// ``trailing`` is a list of items placed at the right end: ``trailing: [IconButton {}]``.
Rectangle {
    id: strip

    property var tabs: []
    property string activeId: ""
    property var groupId: 0
    property bool focused: false
    property bool switcher: false
    property var switcherEntries: []
    property bool compact: false
    property alias trailing: trailingRow.data
    readonly property bool overflowing: tabList.contentWidth > width - trailingRow.width - 8
        - (switcher ? 36 : 0)
    signal tabClicked(string tabId)
    signal tabClosed(string tabId)
    signal tabKept(string tabId)
    signal tabMoved(string tabId, int toIndex)
    signal tabDropped(var payload, int toIndex)
    signal switcherChosen(string windowId)
    signal emptyClicked()

    function iconFor(tab) {
        return tab.kind === "folder" ? "folder"
            : tab.kind === "playlist" ? "playlists"
            : tab.kind === "convert" ? "convert"
            : tab.kind === "tasks" ? "tasks"
            : tab.kind === "artists" || tab.kind === "artist" ? "artists"
            : tab.kind === "profile" ? "profile"
            : tab.kind === "settings" ? "settings"
            : tab.kind === "plugin" ? "plugins"
            : tab.icon || "settings"
    }

    height: Theme.tabHeight
    color: Theme.sidebar

    IconButton {
        id: switcherButton
        objectName: "tabSwitcherButton"
        visible: strip.switcher
        width: visible ? 28 : 0
        height: 28
        anchors.left: parent.left
        anchors.leftMargin: visible ? 4 : 0
        anchors.verticalCenter: parent.verticalCenter
        icon: "grid"
        iconSize: 16
        tip: "Windows"
        onClicked: switcherMenu.popup(switcherButton, 0, height)
    }

    ListView {
        id: tabList
        objectName: "tabStripList"
        anchors.left: switcherButton.right
        anchors.leftMargin: strip.switcher ? 4 : 0
        anchors.right: trailingRow.left
        anchors.rightMargin: overflowButton.visible ? 30 : 0
        height: parent.height
        orientation: ListView.Horizontal
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        // A drag on a tab moves the tab, not the strip: the wheel scrolls the strip.
        interactive: false
        model: strip.tabs

        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: (event) => {
                const room = Math.max(0, tabList.contentWidth - tabList.width)
                const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x
                tabList.contentX = Math.max(0, Math.min(room, tabList.contentX - delta))
            }
        }

        MouseArea {
            parent: tabList
            x: Math.min(tabList.width, Math.max(0, tabList.contentWidth - tabList.contentX))
            width: Math.max(0, tabList.width - x)
            height: tabList.height
            z: 10
            acceptedButtons: Qt.LeftButton
            onClicked: strip.emptyClicked()
        }

        delegate: Item {
            id: tab

            required property var modelData
            required property int index
            readonly property bool isActive: modelData.id === strip.activeId
            readonly property bool dropHover: tabDrop.containsDrag

            objectName: "stripTab_" + modelData.id
            width: Math.min(220, tabRow.implicitWidth + 44)
            height: Theme.tabHeight
            clip: true

            Rectangle {
                width: parent.width
                height: parent.height + Theme.radiusControl
                radius: Theme.radiusControl
                color: tab.isActive ? Theme.editor
                    : tabHover.hovered || tab.dropHover ? Theme.chrome : "transparent"
            }

            Rectangle {
                visible: tab.isActive
                x: Theme.radiusControl
                width: parent.width - 2 * Theme.radiusControl
                height: 2
                color: strip.focused ? Theme.primary : Theme.textMuted
            }

            DropArea {
                id: tabDrop
                anchors.fill: parent
                keys: ["mtee-tab"]
                onDropped: (drop) => {
                    const payload = drop.source.payload
                    if (!payload || payload.tabId === tab.modelData.id)
                        return
                    if (payload.groupId === strip.groupId)
                        strip.tabMoved(payload.tabId, tab.index)
                    else
                        strip.tabDropped(payload, tab.index)
                }
            }

            HoverHandler {
                id: tabHover
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton
                onTapped: strip.tabClicked(tab.modelData.id)
                onDoubleTapped: {
                    if (tab.modelData.preview)
                        strip.tabKept(tab.modelData.id)
                }
            }

            TapHandler {
                acceptedButtons: Qt.MiddleButton
                onTapped: strip.tabClosed(tab.modelData.id)
            }

            DragHandler {
                id: tabDrag
                target: null
                acceptedButtons: Qt.LeftButton
                dragThreshold: 8
                onActiveChanged: if (!active) ghost.Drag.drop()
            }

            Row {
                id: tabRow
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Icon {
                    anchors.verticalCenter: parent.verticalCenter
                    name: strip.iconFor(tab.modelData)
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
                objectName: "stripTabClose_" + tab.modelData.id
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                width: 20
                height: 20
                visible: tab.isActive || tabHover.hovered || hovered
                icon: "close"
                iconSize: 14
                tip: "Close"
                onClicked: strip.tabClosed(tab.modelData.id)
            }

            // The copy that follows the pointer; it lives in the overlay so it can leave the strip.
            Rectangle {
                id: ghost
                objectName: "stripTabGhost"
                property var payload: ({ "type": "tab", "groupId": strip.groupId, "tabId": tab.modelData.id })
                parent: strip.Window.contentItem
                visible: tabDrag.active
                width: 160
                height: 28
                radius: Theme.radiusControl
                color: Theme.surface
                border.width: 1
                border.color: Theme.primary
                z: 2000
                x: tabDrag.centroid.scenePosition.x - width / 2
                y: tabDrag.centroid.scenePosition.y - height / 2
                enabled: false
                Drag.active: tabDrag.active
                Drag.source: ghost
                Drag.keys: ["mtee-tab"]
                Drag.supportedActions: Qt.MoveAction
                Drag.hotSpot.x: width / 2
                Drag.hotSpot.y: height / 2

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    verticalAlignment: Text.AlignVCenter
                    text: tab.modelData.title
                    elide: Text.ElideRight
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }
    }

    IconButton {
        id: overflowButton
        objectName: "tabOverflowButton"
        visible: strip.overflowing
        width: 28
        height: 28
        anchors.right: trailingRow.left
        anchors.rightMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        icon: "chevron-down"
        iconSize: 16
        tip: "All tabs"
        onClicked: overflowMenu.popup(overflowButton, 0, height)
    }

    Row {
        id: trailingRow
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
    }

    AppMenu {
        id: overflowMenu
        objectName: "tabOverflowMenu"

        Instantiator {
            model: strip.tabs
            delegate: AppMenuItem {
                required property var modelData
                text: modelData.title
                mark: modelData.id === strip.activeId
                onTriggered: strip.tabClicked(modelData.id)
            }
            onObjectAdded: (index, object) => overflowMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => overflowMenu.removeItem(object)
        }
    }

    AppMenu {
        id: switcherMenu
        objectName: "tabSwitcherMenu"

        Instantiator {
            model: strip.switcherEntries
            delegate: AppMenuItem {
                required property var modelData
                text: modelData.title
                onTriggered: strip.switcherChosen(modelData.id)
            }
            onObjectAdded: (index, object) => switcherMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => switcherMenu.removeItem(object)
        }
    }
}
