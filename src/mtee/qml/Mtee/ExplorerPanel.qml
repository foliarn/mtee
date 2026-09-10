import QtQuick
import Mtee

// Folder explorer on the left. The foundation step draws invented roots; the
// explorer step fills them from the folders chosen by the user.
Panel {
    id: explorer

    property var roots: []

    SectionLabel {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        text: "Explorer"
    }

    ListView {
        id: tree
        anchors.top: header.bottom
        anchors.topMargin: Theme.spacingSmall
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: addFolder.top
        anchors.bottomMargin: Theme.spacing
        clip: true
        model: explorer.roots
        boundsBehavior: Flickable.StopAtBounds

        delegate: Rectangle {
            id: node
            required property int index
            required property var modelData

            width: tree.width
            height: Theme.rowHeight
            color: hover.hovered ? Theme.hover : "transparent"

            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.leftMargin: Theme.spacing + (node.modelData.depth * Theme.spacing)
                anchors.rightMargin: Theme.spacing
                elide: Text.ElideRight
                text: node.modelData.name
                color: node.modelData.depth === 0 ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            HoverHandler { id: hover }
        }
    }

    ToolButton {
        id: addFolder
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacing
        text: "Add folder"
        enabledAction: false
    }
}
