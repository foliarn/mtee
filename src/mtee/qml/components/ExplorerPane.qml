import QtQuick
import Mtee

Panel {
    id: explorer

    property var roots: []
    signal folderSelected(string folder)

    SectionLabel {
        id: heading
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        text: "Folders"
    }

    Text {
        id: hint
        anchors.top: heading.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        text: "Your collection"
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeBody
    }

    ListView {
        id: tree
        anchors.top: hint.bottom
        anchors.topMargin: Theme.spacing
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: addFolder.top
        anchors.bottomMargin: Theme.spacing
        clip: true
        model: explorer.roots
        boundsBehavior: Flickable.StopAtBounds

        delegate: Rectangle {
            id: node
            required property var modelData
            width: tree.width
            height: Theme.rowHeight
            radius: Theme.controlRadius
            color: nodeHover.hovered ? Theme.hover : "transparent"

            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: Theme.spacing + node.modelData.depth * Theme.spacing
                anchors.rightMargin: Theme.spacing
                text: (node.modelData.depth > 0 ? "▸  " : "▾  ") + node.modelData.name
                color: node.modelData.depth === 0 ? Theme.textPrimary : Theme.textSecondary
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            HoverHandler { id: nodeHover }
            MouseArea {
                anchors.fill: parent
                onClicked: explorer.folderSelected(node.modelData.name)
            }
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
