import QtQuick
import Mtee

Column {
    id: field

    property string label: ""
    property string value: ""
    property bool mixed: false
    signal committed(string value)

    width: 240
    spacing: 5

    Text {
        text: field.label
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Rectangle {
        width: parent.width
        height: 34
        radius: Theme.controlRadius
        color: input.activeFocus ? Theme.activeSurface : Theme.background
        border.width: input.activeFocus ? 2 : 1
        border.color: input.activeFocus ? Theme.accent : Theme.border

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingSmall
            anchors.rightMargin: Theme.spacingSmall
            verticalAlignment: TextInput.AlignVCenter
            text: field.value
            selectByMouse: true
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            clip: true
            onEditingFinished: field.committed(text)

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: input.text.length === 0 && !input.activeFocus
                text: field.mixed ? "Mixed values" : "—"
                color: field.mixed ? Theme.accent : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }
        }
    }
}
