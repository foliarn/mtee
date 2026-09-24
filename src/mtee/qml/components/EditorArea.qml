import QtQuick
import Mtee

// One or two tab groups side by side. Below the single-group width only the
// active group is shown; its tab strip offers a switch to the other one.
Item {
    id: area

    required property var workspace
    property bool singleGroup: false
    property int bottomInset: 0
    readonly property var groups: workspace.groups

    objectName: "editorArea"

    function selectAll() {
        const group = repeater.itemAt(workspace.activeGroup)
        if (group)
            group.selectAll()
    }

    Row {
        anchors.fill: parent

        Repeater {
            id: repeater
            model: area.groups.length

            delegate: EditorGroup {
                required property int index
                workspace: area.workspace
                groupIndex: index
                groupData: area.groups[index] || { "tabs": [], "active": "" }
                groupCount: area.groups.length
                singleGroup: area.singleGroup
                bottomInset: area.bottomInset
                visible: !area.singleGroup || index === area.workspace.activeGroup
                width: area.singleGroup || area.groups.length < 2 ? area.width : area.width / area.groups.length
                height: area.height
            }
        }
    }

    EmptyEditor {
        anchors.fill: parent
        visible: area.groups.length === 0
    }
}
