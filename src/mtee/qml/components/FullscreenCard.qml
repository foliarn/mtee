import QtQuick
import Mtee

// Neutral rounded card of the second page of the fullscreen player: a heading and
// a body that fills the rest.
Rectangle {
    id: card

    property string heading: ""
    default property alias content: body.data
    readonly property real bodyHeight: body.height

    color: Theme.surface
    radius: Theme.fsCardRadius

    Text {
        x: 20
        y: 16
        text: card.heading
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeTitle
        font.bold: true
    }

    Item {
        id: body
        x: 20
        y: 56
        width: card.width - 40
        height: card.height - 56 - 16
    }
}
