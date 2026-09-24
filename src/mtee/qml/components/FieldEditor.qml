import QtQuick
import Mtee

// One editable tag. Enter or leaving the field commits; Escape restores the
// value shown before editing. ``Mixed values`` is a placeholder, never a value.
Column {
    id: field

    property string label: ""
    property string value: ""
    property bool mixed: false
    signal committed(string value)

    spacing: 4

    Text {
        text: field.label
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Rectangle {
        width: parent.width
        height: 32
        color: input.activeFocus ? Theme.editor : Theme.chrome
        border.width: 1
        border.color: input.activeFocus ? Theme.focus : inputMouse.containsMouse ? Theme.textMuted : Theme.separator

        MouseArea {
            id: inputMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.IBeamCursor
            onClicked: input.forceActiveFocus()
        }

        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            verticalAlignment: TextInput.AlignVCenter
            text: field.value
            selectByMouse: true
            color: Theme.textPrimary
            selectionColor: Theme.primary
            selectedTextColor: Theme.textOnColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            clip: true
            onEditingFinished: {
                if (text !== field.value && !(field.mixed && text.length === 0))
                    field.committed(text)
            }
            Keys.onEscapePressed: {
                text = field.value
                focus = false
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: input.text.length === 0 && !input.activeFocus
                text: field.mixed ? "Mixed values" : "—"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.italic: field.mixed
            }
        }
    }
}
