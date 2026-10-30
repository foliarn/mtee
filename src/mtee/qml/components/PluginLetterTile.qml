import QtQuick
import Mtee

// The letter that stands for a plugin until plugins ship an icon: a square with the first letter
// of its title, on the surface colour with a separator border.
Rectangle {
    id: tile

    property string letter: ""
    property int tileSize: 20

    width: tileSize
    height: tileSize
    color: Theme.surface
    border.width: 1
    border.color: Theme.separator

    Text {
        anchors.centerIn: parent
        text: tile.letter
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: tile.tileSize >= 32 ? Theme.fontSizeSecondary : Theme.fontSizeCaption
        font.weight: Font.DemiBold
    }
}
