import QtQuick
import QtQuick.Controls.Basic
import Mtee

ComboBox {
    id: control
    implicitHeight: 36
    leftPadding: 12
    rightPadding: 28
    background: Rectangle {
        color: Theme.surface
        border.color: control.activeFocus ? Theme.focus : Theme.separator
    }
    contentItem: TextInput {
        text: control.editable ? control.editText : control.displayText
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        readOnly: !control.editable
        clip: true
        onTextEdited: control.editText = text
    }
    indicator: Text {
        x: control.width - 24; anchors.verticalCenter: parent.verticalCenter
        text: "v"; color: Theme.textSecondary; font.pixelSize: 12
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width
        contentItem: Text { text: modelData; color: Theme.textPrimary; font.pixelSize: 13; elide: Text.ElideRight }
        background: Rectangle { color: parent.highlighted ? Theme.selection : Theme.surface }
        highlighted: control.highlightedIndex === index
    }
    popup: Popup {
        y: control.height; width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight + 2, 260)
        padding: 1
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollBar.vertical: ScrollBar {}
        }
        background: Rectangle { color: Theme.surface; border.color: Theme.separator }
    }
}
