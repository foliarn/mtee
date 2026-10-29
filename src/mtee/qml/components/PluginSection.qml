import QtQuick
import Mtee

// A SidebarSection of a plugin. The header is the PaneHeader of a sidebar pane (uppercase
// caption, actions on the right) with a chevron; the rows are the rows of the Explorer tree
// (24 px, chevron for groups, muted counts on the right). The rows come from the plugin's
// model, the actions and the click from the plugin through ``workspace.pluginUi``.
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
                delegate: IconButton {
                    required property var modelData
                    objectName: "pluginSectionAction_" + modelData.id
                    icon: modelData.icon; iconSize: 16; width: 26; height: 26; tip: modelData.tip
                    onClicked: section.workspace.pluginUi.runSectionAction(section.sectionKey, modelData.id)
                }
            }
        }
    }

    Repeater {
        model: section.expanded ? section.visibleItems : []

        delegate: Rectangle {
            id: row
            required property var modelData
            readonly property bool isGroup: modelData.kind === "group"
            readonly property bool current: !isGroup && modelData.id === section.activeId
            readonly property bool hasIcon: isGroup || (modelData.icon || "").length > 0

            objectName: "pluginRow_" + modelData.id
            width: section.width
            height: Theme.treeRowHeight
            color: current ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"

            Icon {
                id: lead
                x: 8 + (row.modelData.depth || 0) * 14
                anchors.verticalCenter: parent.verticalCenter
                visible: row.hasIcon
                name: row.isGroup ? (section.isFolded(row.modelData) ? "chevron-right" : "chevron-down")
                    : (row.modelData.icon || "")
                size: row.isGroup ? 16 : 14
                color: row.isGroup ? Theme.textSecondary
                    : row.modelData.tone === "secondary" ? Theme.secondary : Theme.textSecondary
            }

            Text {
                anchors.left: lead.visible ? lead.right : parent.left
                anchors.leftMargin: lead.visible ? (row.isGroup ? 4 : 8) : 8 + (row.modelData.depth || 0) * 14 + 22
                anchors.right: tail.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: row.modelData.name
                elide: Text.ElideRight
                color: row.current ? Theme.primary : row.isGroup ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.weight: row.isGroup && (row.modelData.depth || 0) === 0 ? Font.DemiBold : Font.Normal
            }

            Item {
                id: tail
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                width: tailRow.width
                height: parent.height

                Row {
                    id: tailRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    // A count the plugin wants noticed, in the accent colour as on the activity bar.
                    Rectangle {
                        visible: (row.modelData.badge || 0) > 0
                        anchors.verticalCenter: parent.verticalCenter
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

                    Text {
                        visible: (row.modelData.count || "").length > 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: row.modelData.count || ""
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        font.features: { "tnum": 1 }
                    }
                }
            }

            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    if (row.isGroup) {
                        const next = Object.assign({}, section.folded)
                        next[row.modelData.id] = !section.isFolded(row.modelData)
                        section.folded = next
                    } else {
                        section.workspace.pluginUi.activateRow(section.sectionKey, row.modelData.id)
                    }
                }
            }
        }
    }
}
