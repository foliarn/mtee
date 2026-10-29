import QtQuick
import Mtee

// A short code to read out or type elsewhere, such as a device login code.
Rectangle {
    id: badge

    property string text: ""

    implicitWidth: codeText.implicitWidth + 28
    implicitHeight: 32
    color: Theme.surface
    border.width: 1
    border.color: Theme.separator

    Text {
        id: codeText
        anchors.centerIn: parent
        text: badge.text
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeTitle
        font.weight: Font.DemiBold
        font.letterSpacing: 2
    }
}
