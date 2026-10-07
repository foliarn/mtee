import QtQuick
import Mtee

// Toggle chip of a filter bar: lime outline and text when chosen.
Rectangle {
    id: chip

    property string text: ""
    property bool checked: false
    signal toggled()

    implicitWidth: label.implicitWidth + 24
    implicitHeight: 26
    color: chip.checked ? Qt.rgba(0.776, 1, 0.102, 0.12) : hit.containsMouse ? Theme.surface : "transparent"
    border.width: 1
    border.color: chip.checked ? Theme.primary : Theme.separator
    activeFocusOnTab: true
    Keys.onSpacePressed: chip.toggled()
    Keys.onReturnPressed: chip.toggled()

    Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: chip.activeFocus
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: chip.text
        color: chip.checked ? Theme.primary : Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
        font.weight: chip.checked ? Font.DemiBold : Font.Normal
    }

    MouseArea {
        id: hit
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.toggled()
    }
}
