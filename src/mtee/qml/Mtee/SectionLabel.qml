import QtQuick
import Mtee

// Name of a zone: small, secondary, letter-spaced.
Text {
    color: Theme.textSecondary
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSmall
    font.letterSpacing: 0.6
    font.capitalization: Font.AllUppercase
    elide: Text.ElideRight
}
