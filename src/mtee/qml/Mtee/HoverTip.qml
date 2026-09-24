import QtQuick
import QtQuick.Controls.Basic

ToolTip {
    id: tip

    delay: 600
    timeout: 6000
    padding: 6
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSmall

    contentItem: Text {
        text: tip.text
        color: Theme.textPrimary
        font: tip.font
    }

    background: Rectangle {
        color: Theme.surface
        border.width: 1
        border.color: Theme.separator
    }
}
