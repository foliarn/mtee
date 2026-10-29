import QtQuick
import Mtee

// A settings row: a label, a description and an on/off switch on the right.
Item {
    id: toggleRow

    property string label: ""
    property string description: ""
    property bool checked: false
    signal toggled(bool checked)

    width: parent ? parent.width : 0
    height: Math.max(52, texts.implicitHeight + 16)

    Column {
        id: texts
        anchors.left: parent.left
        anchors.right: toggle.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: toggleRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: toggleRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    ToggleSwitch {
        id: toggle
        objectName: "toggle_" + toggleRow.objectName
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: toggleRow.checked
        onToggled: (checked) => toggleRow.toggled(checked)
    }
}
