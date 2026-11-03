import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The sidebar of an activity that a plugin owns: the pane header with the plugin's actions, its
// sections (one without a header of its own), and an optional foot of text lines. Everything
// comes from the plugin's contributions through ``workspace.pluginUi``.
Item {
    id: pane

    required property var workspace
    // "<plugin_id>.<activity_id>"
    required property string activity
    readonly property var ui: workspace.pluginUi
    readonly property var info: ui.activityInfo(activity)
    readonly property var foot: ui.activityFoot(activity)
    objectName: "pluginPane"

    PaneHeader {
        id: header
        width: parent.width
        title: pane.info.title

        Repeater {
            model: pane.info.actions
            // A hidden button takes no place in the header; a button with a label is a text button.
            delegate: Item {
                id: slot
                required property var modelData
                readonly property bool hasLabel: (modelData.label || "").length > 0
                visible: pane.ui.actionShown("activity:" + pane.activity, modelData.id, pane.ui.revision)
                width: hasLabel ? textAction.implicitWidth : 26
                height: 26

                IconButton {
                    objectName: "pluginPaneAction_" + slot.modelData.id
                    visible: !slot.hasLabel
                    icon: slot.modelData.icon; iconSize: 16; width: 26; height: 26; tip: slot.modelData.tip
                    onClicked: pane.ui.runActivityAction(pane.activity, slot.modelData.id)
                }

                TextButton {
                    id: textAction
                    objectName: "pluginPaneLabelAction_" + slot.modelData.id
                    visible: slot.hasLabel
                    kind: "ghost"
                    text: slot.modelData.label || ""
                    tip: slot.modelData.tip
                    height: 26
                    onClicked: pane.ui.runActivityAction(pane.activity, slot.modelData.id)
                }
            }
        }
    }

    Flickable {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: status.top
        contentHeight: sectionColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        PluginSections {
            id: sectionColumn
            width: parent.width
            workspace: pane.workspace
            activity: pane.activity
            coreActivity: false
        }
    }

    Rectangle {
        id: status
        visible: pane.foot !== null && pane.foot.count > 0
        anchors.bottom: parent.bottom
        width: parent.width
        height: visible ? statusColumn.implicitHeight + 24 : 0
        color: "transparent"

        Rectangle {
            width: parent.width
            height: 1
            color: Theme.separator
            opacity: 0.6
        }

        Column {
            id: statusColumn
            x: 16
            y: 12
            width: parent.width - 32
            spacing: 3

            Repeater {
                model: pane.foot
                delegate: Text {
                    required property var modelData
                    width: statusColumn.width
                    text: modelData.text
                    elide: Text.ElideRight
                    color: modelData.tone === "warning" ? Theme.warning
                        : modelData.tone === "muted" ? Theme.textMuted : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
        }
    }
}
