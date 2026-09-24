import QtQuick
import QtQuick.Controls.Basic

ScrollBar {
    id: bar

    policy: ScrollBar.AsNeeded
    padding: 0
    minimumSize: 0.06

    contentItem: Rectangle {
        implicitWidth: 8
        implicitHeight: 8
        color: bar.pressed ? Qt.rgba(1, 1, 1, 0.32) : bar.hovered ? Qt.rgba(1, 1, 1, 0.22) : Qt.rgba(1, 1, 1, 0.12)
        opacity: bar.active || bar.hovered ? 1.0 : 0.0

        Behavior on opacity { NumberAnimation { duration: 160 } }
    }

    background: Item {}
}
