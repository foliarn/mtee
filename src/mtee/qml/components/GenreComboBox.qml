import QtQuick
import QtQuick.Controls.Basic
import Mtee

ComboBox {
    id: control
    implicitHeight: 34
    implicitWidth: 200
    contentItem: Text {
        leftPadding: 10; rightPadding: 26
        text: control.displayText
        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary
        color: control.enabled ? Theme.textPrimary : Theme.textMuted
        verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
    }
    indicator: Text { x: control.width - 22; anchors.verticalCenter: parent.verticalCenter; text: "⌄"; color: Theme.textSecondary }
    background: Rectangle { color: Theme.surface; border.color: control.activeFocus ? Theme.focus : Theme.separator; radius: 3 }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: control.width
        contentItem: Text { text: typeof modelData === "string" ? modelData : modelData[control.textRole]; color: Theme.textPrimary; font.family: Theme.fontFamily; elide: Text.ElideRight }
        highlighted: control.highlightedIndex === index
        background: Rectangle { color: parent.highlighted ? Theme.selection : Theme.surface }
    }
    popup: Popup {
        y: control.height + 2
        width: control.width
        implicitHeight: Math.min(contentItem.implicitHeight,300)
        padding: 1
        contentItem: ListView { clip: true; implicitHeight: contentHeight; model: control.popup.visible ? control.delegateModel : null; currentIndex: control.highlightedIndex; ScrollBar.vertical: ThinScrollBar {} }
        background: Rectangle { color: Theme.surface; border.color: Theme.separator }
    }
}
