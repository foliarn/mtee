import QtQuick
import Mtee

GridView {
    id: grid

    property var workspace
    property int cardWidth: 180
    cellWidth: cardWidth
    cellHeight: 190
    clip: true
    model: grid.workspace ? grid.workspace.tracks : []
    boundsBehavior: Flickable.StopAtBounds

    delegate: Item {
        id: card
        required property int index
        required property var modelData
        width: grid.cardWidth
        height: grid.cellHeight

        Rectangle {
            id: artwork
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: width
            radius: Theme.panelRadius
            color: Theme.activeSurface
            border.width: grid.workspace.selectedRows.indexOf(card.index) >= 0 ? 2 : 1
            border.color: grid.workspace.selectedRows.indexOf(card.index) >= 0 ? Theme.accent : Theme.border

            Text {
                anchors.centerIn: parent
                text: (grid.workspace.noArtwork || !card.modelData.artwork) ? "No artwork" : "Artwork"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Rectangle {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                width: 4
                height: parent.height
                color: Theme.accent
                visible: grid.workspace.playingRow === card.index
            }

            MouseArea {
                anchors.fill: parent
                onClicked: grid.workspace.selectRow(card.index, mouse.modifiers & Qt.ControlModifier)
                onDoubleClicked: grid.workspace.playRow(card.index)
            }
        }

        Text {
            anchors.top: artwork.bottom
            anchors.topMargin: Theme.spacingSmall
            anchors.left: parent.left
            anchors.right: parent.right
            text: card.modelData.title
            color: Theme.textPrimary
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            anchors.top: parent.top
            anchors.topMargin: artwork.height + Theme.spacingSmall + 20
            anchors.left: parent.left
            anchors.right: parent.right
            text: card.modelData.artist === "" ? "Artist missing" : card.modelData.artist
            color: card.modelData.artist === "" ? Theme.danger : Theme.textSecondary
            elide: Text.ElideRight
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
