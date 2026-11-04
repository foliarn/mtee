import QtQuick
import Mtee

// A SidebarSection of a plugin. The header is the PaneHeader of a sidebar pane (uppercase
// caption, a count badge, actions on the right) with a chevron; the rows are the rows of the
// Explorer tree (24 px, chevron for groups, muted counts on the right). The rows come from the
// plugin's model, the actions and the click from the plugin through ``workspace.pluginUi``.
// A warning row is drawn in the warning colour, icon included; a group folds by its chevron and
// a click on its name is the plugin's ``activate``.
Column {
    id: section

    required property var workspace
    // The identity of the section for the core: "<plugin_id>.<section_id>".
    property string sectionKey: ""
    property string title: ""
    property var actions: []
    property bool expanded: true
    property bool showHeader: true
    // The rows of the plugin's PluginRowsModel as one list.
    property var items: []
    // The reference of the active editor tab: the row with the same id is the current one.
    property string activeId: ""
    // Groups the user folded or unfolded: id -> true (folded) or false. A group with no entry
    // follows the plugin's ``expanded`` value.
    property var folded: ({})
    // "compact" (tree rows) or "regular" (the Playlists list): the size of the NavItem rows.
    property string rowSize: "compact"
    readonly property var ui: workspace.pluginUi
    // The count the plugin declared for the section, read again with the plugins' revision.
    readonly property int headerCount: ui ? ui.sectionCount(sectionKey, ui.revision) : 0

    function isFolded(item) {
        return section.folded[item.id] !== undefined ? section.folded[item.id] : item.expanded === false
    }

    readonly property var visibleItems: {
        const rows = []
        let hiddenDepth = -1
        for (const item of items) {
            const depth = item.depth || 0
            if (hiddenDepth >= 0 && depth > hiddenDepth)
                continue
            hiddenDepth = -1
            rows.push(item)
            if (item.kind === "group" && section.isFolded(item))
                hiddenDepth = depth
        }
        return rows
    }

    // The state of the section the first time it is shown; after that the user's choice is kept.
    Component.onCompleted: section.expanded = section.ui.sectionStartsExpanded(section.sectionKey)

    objectName: "pluginSection_" + sectionKey
    width: parent ? parent.width : 240

    Item {
        visible: section.showHeader
        width: parent.width
        height: section.showHeader ? Theme.treeRowHeight + 12 + 1 : 0

        Rectangle {
            width: parent.width
            height: 1
            color: Theme.separator
            opacity: 0.6
        }

        Icon {
            x: 10
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            name: section.expanded ? "chevron-down" : "chevron-right"
            size: 14
            color: Theme.textSecondary
        }

        Text {
            id: titleText
            x: 30
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            text: section.title.toUpperCase()
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeCaption
            font.weight: Font.DemiBold
            font.letterSpacing: 1.1
        }

        // The count of the section, in the accent colour as the badge of an activity; hidden at 0.
        Rectangle {
            objectName: "pluginSectionCount_" + section.sectionKey
            visible: section.headerCount > 0
            x: titleText.x + titleText.implicitWidth + 6
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            width: Math.max(14, countText.implicitWidth + 6)
            height: 14
            color: Theme.primary

            Text {
                id: countText
                anchors.centerIn: parent
                text: section.headerCount
                color: Theme.textOnColor
                font.family: Theme.fontFamily
                font.pixelSize: 10
                font.weight: Font.Bold
            }
        }

        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: actionRow.visible ? actionRow.width + 8 : 0
            cursorShape: Qt.PointingHandCursor
            onClicked: section.expanded = !section.expanded
        }

        Row {
            id: actionRow
            visible: section.actions.length > 0
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 1
            spacing: 2

            Repeater {
                model: section.actions
                // A hidden button takes no place in the row; a button with a label is a text button.
                delegate: Item {
                    id: slot
                    required property var modelData
                    readonly property bool hasLabel: (modelData.label || "").length > 0
                    visible: section.ui.actionShown("section:" + section.sectionKey, modelData.id, section.ui.revision)
                    width: hasLabel ? textAction.implicitWidth : 26
                    height: 26

                    IconButton {
                        objectName: "pluginSectionAction_" + slot.modelData.id
                        visible: !slot.hasLabel
                        icon: slot.modelData.icon; iconSize: 16; width: 26; height: 26; tip: slot.modelData.tip
                        onClicked: section.ui.runSectionAction(section.sectionKey, slot.modelData.id)
                    }

                    TextButton {
                        id: textAction
                        objectName: "pluginSectionLabelAction_" + slot.modelData.id
                        visible: slot.hasLabel
                        kind: "ghost"
                        text: slot.modelData.label || ""
                        tip: slot.modelData.tip
                        height: 26
                        onClicked: section.ui.runSectionAction(section.sectionKey, slot.modelData.id)
                    }
                }
            }
        }
    }

    Repeater {
        model: section.expanded ? section.visibleItems : []

        // A row is the NavItem of the Playlists list (plan 132.4): the same height, tile and hover
        // as the playlists. A group folds by its chevron; a click on the row is the plugin's activate.
        delegate: NavItem {
            id: row
            required property var modelData
            readonly property bool isGroup: modelData.kind === "group"
            readonly property bool current: !isGroup && modelData.id === section.activeId

            objectName: "pluginRow_" + modelData.id
            width: section.width
            size: section.rowSize
            height: size === "compact" ? 28 : 52
            depth: modelData.depth || 0
            title: modelData.name || ""
            leading: isGroup ? "" : (modelData.icon || "")
            expandable: isGroup
            expanded: isGroup && !section.isFolded(modelData)
            accent: current
            warning: modelData.tone === "warning"
            trailingText: modelData.count || ""
            trailingTone: warning ? "danger" : "muted"
            trailing: Rectangle {
                objectName: "pluginRowBadge_" + row.modelData.id
                visible: (row.modelData.badge || 0) > 0
                width: Math.max(14, badgeText.implicitWidth + 6)
                height: 14
                color: Theme.primary

                Text {
                    id: badgeText
                    anchors.centerIn: parent
                    text: row.modelData.badge || ""
                    color: Theme.textOnColor
                    font.family: Theme.fontFamily
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
            }

            onClicked: {
                // The references are taken first: folding rebuilds this delegate.
                const ui = section.ui
                const key = section.sectionKey
                ui.activateRow(key, row.modelData.id)
            }
            onChevronClicked: {
                const ui = section.ui
                const key = section.sectionKey
                const item = row.modelData
                const expanded = section.isFolded(item)
                const next = Object.assign({}, section.folded)
                next[item.id] = !expanded
                section.folded = next
                ui.foldRow(key, item.id, expanded)
            }
        }
    }
}
