import QtQuick
import Mtee

// A settings row: a label, a description and a read-only value on the right.
Item {
    id: infoRow

    property string label: ""
    property string description: ""
    property string value: ""

    width: parent ? parent.width : 0
    height: Math.max(52, infoTexts.implicitHeight + 16)

    Column {
        id: infoTexts
        anchors.left: parent.left
        anchors.right: infoValue.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: infoRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: infoRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Text {
        id: infoValue
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: infoRow.value
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }
}
