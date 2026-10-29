import QtQuick
import Mtee

// The dialog of the sample plugin. The core draws the popup; this file is its content. Every
// property below is set by the core after loading, so a binding must read them with a fallback.
Column {
    id: dialogRoot

    property var workspace
    property var backend
    property var dialog
    property string ref: ""

    objectName: "sampleDialog"
    spacing: 16

    Text {
        objectName: "sampleDialogTitle"
        width: parent.width
        text: "Sample dialog: " + dialogRoot.ref
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 24
        font.weight: Font.Bold
    }

    TextButton {
        objectName: "sampleDialogClose"
        text: "Close"
        kind: "ghost"
        onClicked: dialogRoot.dialog.close()
    }
}
