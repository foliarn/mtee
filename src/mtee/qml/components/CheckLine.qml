import QtQuick
import Mtee

// Square check box with a label, in the style of the other controls.
Item {
    id: line

    property string text: ""
    property string hint: ""
    property bool checked: false
    signal toggled(bool checked)

    implicitHeight: hint.length > 0 ? 44 : 24
    implicitWidth: 320
    activeFocusOnTab: true

    Rectangle {
        id: box
        width: 16
        height: 16
        y: 4
        color: line.checked ? Theme.primary : "transparent"
        border.width: 1
        border.color: line.checked ? Theme.primary : Theme.textMuted

        Icon {
            anchors.centerIn: parent
            visible: line.checked
            name: "check"
            size: 14
            color: Theme.textOnColor
        }
    }

    Column {
        anchors.left: box.right
        anchors.leftMargin: 10
        anchors.right: parent.right
        y: 2
        spacing: 2

        Text {
            width: parent.width
            text: line.text
            wrapMode: Text.Wrap
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            visible: line.hint.length > 0
            width: parent.width
            text: line.hint
            wrapMode: Text.Wrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Rectangle {
        anchors.fill: box
        anchors.margins: -3
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: line.activeFocus
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: line.toggled(!line.checked)
    }

    Keys.onSpacePressed: toggled(!checked)
}
