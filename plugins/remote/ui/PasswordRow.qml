import QtQuick
import QtQuick.Controls.Basic
import Mtee

// A settings row with a masked text field: the same layout as FieldRow of the core, with the
// characters hidden. The text is read by the page when the person presses Connect and is never
// saved; the page clears it straight after.
Item {
    id: passwordRow

    property string label: ""
    property string description: ""
    property string placeholder: ""
    property alias text: passwordField.text

    function clear() {
        passwordField.text = ""
    }

    width: parent ? parent.width : 0
    height: Math.max(60, passwordTexts.implicitHeight + 16)

    Column {
        id: passwordTexts
        anchors.left: parent.left
        anchors.right: passwordField.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: passwordRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: passwordRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    TextField {
        id: passwordField
        objectName: "remotePasswordField"
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 260
        height: 32
        echoMode: TextInput.Password
        passwordCharacter: "•"
        placeholderText: passwordRow.placeholder
        color: Theme.textPrimary
        placeholderTextColor: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
        selectByMouse: true
        leftPadding: 10
        rightPadding: 10
        background: Rectangle {
            color: Theme.surface
            border.width: 1
            border.color: passwordField.activeFocus ? Theme.focus : Theme.separator
        }
    }
}
