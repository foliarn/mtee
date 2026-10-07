import QtQuick
import Mtee

// One editable tag. In ``drafting`` mode every keystroke is only staged: the value
// is written by the panel's Save button, a marker shows a changed field and the arrow
// restores it. Without ``drafting`` (the demo) Enter or leaving the field commits.
// Escape restores the value shown before editing. ``Mixed values`` is a placeholder,
// never a value.
Column {
    id: field

    property string label: ""
    property string value: ""
    property bool mixed: false
    property bool editable: true
    property string reason: ""
    property bool drafting: false
    property bool dirty: false
    property string error: ""
    property bool multiline: false
    property var suggestions: []
    property bool wasEdited: false
    signal editingStarted()
    signal committed(string value, bool remove)
    signal edited(string text)
    signal reverted()
    signal queryChanged(string text)

    readonly property bool focused: input.activeFocus || area.activeFocus
    readonly property string typed: field.multiline ? area.text : input.text

    spacing: 4

    onValueChanged: {
        if (!field.focused) {
            input.text = value
            area.text = value
            wasEdited = false
        }
    }

    function setText(text) {
        input.text = text
        area.text = text
    }

    function finish(text) {
        if (field.drafting) {
            field.edited(text)
        } else if (field.wasEdited && (text !== field.value || field.mixed)) {
            field.committed(text, text.length === 0)
        }
        field.wasEdited = false
    }

    Item {
        width: parent.width
        height: 20

        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Text {
                id: labelText
                text: field.label
                color: field.error.length > 0 ? Theme.danger : field.dirty ? Theme.primary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Rectangle {
                visible: field.dirty
                anchors.verticalCenter: parent.verticalCenter
                width: 6
                height: 6
                radius: 3
                color: field.error.length > 0 ? Theme.danger : Theme.primary
            }

            Icon {
                visible: !field.editable
                anchors.verticalCenter: parent.verticalCenter
                name: "lock"
                size: 12
                color: Theme.textMuted

                MouseArea {
                    id: lockHover
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                }

                HoverTip {
                    visible: lockHover.containsMouse && field.reason.length > 0
                    text: field.reason
                }
            }
        }

        IconButton {
            visible: field.dirty
            objectName: "revertField"
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 22
            height: 20
            icon: "undo"
            iconSize: 13
            tip: "Restore the original value"
            onClicked: field.reverted()
        }
    }

    Rectangle {
        width: parent.width
        height: field.multiline ? 76 : 32
        color: !field.editable ? Theme.sidebar : field.focused ? Theme.editor : Theme.chrome
        border.width: 1
        border.color: field.error.length > 0 ? Theme.danger
            : field.focused ? Theme.focus
            : field.dirty ? Theme.primary
            : inputMouse.containsMouse ? Theme.textMuted : Theme.separator

        MouseArea {
            id: inputMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: field.editable ? Qt.IBeamCursor : Qt.ArrowCursor
            enabled: field.editable
            onClicked: (field.multiline ? area : input).forceActiveFocus()
        }

        TextInput {
            id: input
            objectName: "fieldEditorInput"
            visible: !field.multiline
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
            onTextEdited: {
                field.wasEdited = true
                field.queryChanged(text)
                if (field.drafting)
                    field.edited(text)
            }
            onEditingFinished: field.finish(text)
            onAccepted: {
                if (field.drafting) {
                    const next = nextItemInFocusChain(true)
                    if (next)
                        next.forceActiveFocus()
                }
            }
            Keys.onEscapePressed: {
                text = field.value
                if (field.drafting)
                    field.edited(text)
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

        TextEdit {
            id: area
            objectName: "fieldEditorArea"
            visible: field.multiline
            anchors.fill: parent
            anchors.margins: 8
            text: field.value
            wrapMode: TextEdit.Wrap
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
                } else {
                    field.finish(text)
                }
            }
            onTextChanged: {
                if (activeFocus) {
                    field.wasEdited = true
                    if (field.drafting)
                        field.edited(text)
                }
            }
            Keys.onEscapePressed: {
                text = field.value
                field.wasEdited = false
                focus = false
            }

            Text {
                visible: area.text.length === 0 && !area.activeFocus
                text: field.mixed ? "Mixed values" : "—"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.italic: field.mixed
            }
        }
    }

    Repeater {
        model: field.focused ? field.suggestions : []

        delegate: Rectangle {
            required property var modelData
            width: field.width
            height: 26
            color: suggestionMouse.containsMouse ? Theme.selection : Theme.surface

            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 10
                width: parent.width - 20
                text: parent.modelData
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            MouseArea {
                id: suggestionMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: (mouse) => {
                    field.setText(parent.modelData)
                    field.edited(parent.modelData)
                    mouse.accepted = true
                }
            }
        }
    }

    Text {
        width: parent.width
        visible: field.error.length > 0
        text: field.error
        color: Theme.danger
        wrapMode: Text.WordWrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }
}
