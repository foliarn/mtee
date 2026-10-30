import QtQuick
import Mtee

// A settings row: a label, a description and a read-only value on the right. The value sits on
// the baseline of the label, not in the middle of the label and the description.
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
            id: infoLabel
            text: infoRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            visible: infoRow.description.length > 0
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
        y: infoTexts.y + infoLabel.y + infoLabel.baselineOffset - infoValue.baselineOffset
        text: infoRow.value
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }
}
