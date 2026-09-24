import QtQuick
import Mtee

// One editable tag. Enter or leaving the field commits; Escape restores the
// value shown before editing. ``Mixed values`` is a placeholder, never a value.
Column {
    id: field

    property string label: ""
    property string value: ""
    property bool mixed: false
    property bool editable: true
    property string reason: ""
    property bool wasEdited: false
    signal editingStarted()
    signal committed(string value, bool remove)

    spacing: 4

    onValueChanged: {
        if (!input.activeFocus) {
            input.text = value
            wasEdited = false
        }
    }

    Text {
        text: field.label
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Rectangle {
        width: parent.width
        height: 32
        color: !field.editable ? Theme.sidebar : input.activeFocus ? Theme.editor : Theme.chrome
        border.width: 1
        border.color: input.activeFocus ? Theme.focus : inputMouse.containsMouse ? Theme.textMuted : Theme.separator

        MouseArea {
            id: inputMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: field.editable ? Qt.IBeamCursor : Qt.ArrowCursor
            enabled: field.editable
            onClicked: input.forceActiveFocus()
        }

        TextInput {
            id: input
            objectName: "fieldEditorInput"
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
            enabled: field.editable
            opacity: field.editable ? 1 : 0.58
            onActiveFocusChanged: {
                if (activeFocus) {
                    field.wasEdited = false
                    field.editingStarted()
                }
            }
            onTextEdited: field.wasEdited = true
            onEditingFinished: {
                if (field.wasEdited && (text !== field.value || field.mixed))
                    field.committed(text, text.length === 0)
                field.wasEdited = false
            }
            Keys.onEscapePressed: {
                text = field.value
                field.wasEdited = false
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

    Text {
        width: parent.width
        visible: !field.editable && field.reason.length > 0
        text: field.reason
        color: Theme.textMuted
        wrapMode: Text.WordWrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }
}
