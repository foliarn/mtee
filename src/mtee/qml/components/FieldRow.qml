import QtQuick
import QtQuick.Controls.Basic
import Mtee

// A settings row: a label, a description and a text field on the right. ``value`` is the text
// shown; ``edited`` carries the text once the user leaves the field or presses Enter.
Item {
    id: fieldRow

    property string label: ""
    property string description: ""
    property string value: ""
    property string placeholder: ""
    signal edited(string value)

    width: parent ? parent.width : 0
    height: Math.max(60, fieldTexts.implicitHeight + 16)

    Column {
        id: fieldTexts
        anchors.left: parent.left
        anchors.right: fieldBox.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: fieldRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: fieldRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    TextField {
        id: fieldBox
        objectName: "field_" + fieldRow.objectName
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 260
        height: 32
        text: fieldRow.value
        placeholderText: fieldRow.placeholder
        color: Theme.textPrimary
        placeholderTextColor: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
        selectByMouse: true
        leftPadding: 10
        rightPadding: 10
        onEditingFinished: fieldRow.edited(text)
        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: fieldBox.activeFocus ? Theme.focus : Theme.separator
        }
    }
}
