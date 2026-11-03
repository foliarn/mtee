import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Asks for the new name of a track's file (plan 130). The workspace opens it with
// ``renameFileRequested``; the extension stays and is not part of the field.
ConfirmDialog {
    id: dialog

    required property var workspace
    property string trackId: ""

    objectName: "renameFileDialog"
    title: "Rename file"
    text: "The extension stays the same. The file is never replaced."
    buttons: [
        { "key": "cancel", "label": "Cancel", "kind": "ghost" },
        { "key": "rename", "label": "Rename", "kind": "primary" }
    ]

    TextField {
        id: nameField
        objectName: "renameFileField"
        width: parent ? parent.width : 300
        height: 32
        selectByMouse: true
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeBody
        onAccepted: dialog.answer("rename")
        background: Rectangle {
            radius: Theme.radius
            color: Theme.chrome
            border.width: 1
            border.color: nameField.activeFocus ? Theme.focus : Theme.separator
        }
    }

    Connections {
        target: dialog.workspace
        function onRenameFileRequested(trackId, name) {
            dialog.trackId = trackId
            nameField.text = name
            dialog.open()
            nameField.forceActiveFocus()
            nameField.selectAll()
        }
    }

    onAnswered: (key) => {
        if (key === "rename")
            dialog.workspace.renameTrackFile(dialog.trackId, nameField.text)
    }
}
