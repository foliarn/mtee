import QtQuick
import Mtee

// One row of the player's "more" menu (plan 131.8): an icon and a label, clicked to trigger.
Rectangle {
    id: row

    property string icon: ""
    property string label: ""
    property bool active: false
    signal triggered()

    height: 32
    radius: Theme.radius
    color: rowMouse.containsMouse ? Theme.selection : "transparent"

    Icon {
        x: 10
        anchors.verticalCenter: parent.verticalCenter
        name: row.icon
        size: 16
        color: row.active ? Theme.primary : Theme.textSecondary
    }

    Text {
        x: 36
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - 8
        text: row.label
        elide: Text.ElideRight
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: row.triggered()
    }
}
