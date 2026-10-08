import QtQuick
import QtQuick.Controls.Basic
import Mtee

CheckBox {
    id: control
    implicitHeight: 32
    indicator: Rectangle {
        x: control.leftPadding; anchors.verticalCenter: parent.verticalCenter
        width: 18; height: 18; radius: 3
        color: control.checked ? Theme.primary : Theme.surface
        border.color: control.activeFocus ? Theme.focus : control.checked ? Theme.primary : Theme.textMuted
        Text { anchors.centerIn: parent; text: "✓"; visible: control.checked; color: Theme.editor; font.pixelSize: 14 }
    }
    contentItem: Text {
        text: control.text
        leftPadding: control.indicator.width + control.spacing
        color: Theme.textSecondary; font.family: Theme.fontFamily; elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
    }
}
