import QtQuick
import Mtee

// A titled group of settings rows: the title, then a rule. Fills the width of its parent column.
Column {
    property string title: ""

    width: parent ? parent.width : 0
    topPadding: 20
    bottomPadding: 4
    spacing: 8

    Text {
        text: parent.title
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeTitle
        font.weight: Font.DemiBold
    }

    Rectangle { width: parent.width; height: 1; color: Theme.separator }
}
