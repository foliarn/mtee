import QtQuick
import QtQuick.Controls.Basic
import Mtee

TextField {
    id: control
    implicitHeight: 34
    implicitWidth: 200
    color: Theme.textPrimary
    placeholderTextColor: Theme.textMuted
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSecondary
    selectByMouse: true
    background: Rectangle { color: Theme.surface; border.color: control.activeFocus ? Theme.focus : Theme.separator; radius: 3 }
}
