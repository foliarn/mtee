import QtQuick
import Mtee

// The centre of the frame (plan 131.7): the window tree of the centre, or the empty watermark when no
// window is open. Below the single-window width only the focused window is drawn; its tab strip offers
// a switch to the others.
Item {
    id: area

    required property var workspace
    property bool singleGroup: false
    property int bottomInset: 0
    readonly property var groups: workspace.groups

    objectName: "editorArea"

    function selectAll() {
        const group = tree.groupItem(workspace.activeGroup)
        if (group)
            group.selectAll()
    }

    WindowTree {
        id: tree
        anchors.fill: parent
        visible: area.groups.length > 0
        workspace: area.workspace
        singleGroup: area.singleGroup
        bottomInset: area.bottomInset
        node: area.singleGroup
            ? ({ "type": "leaf", "group": area.workspace.activeGroup })
            : area.workspace.centerLayout
    }

    WindowSurface {
        anchors.fill: parent
        visible: area.groups.length === 0

        EmptyEditor {
            anchors.fill: parent
        }
    }
}
