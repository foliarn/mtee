import QtQuick

// Square on/off switch; lime track when on.
Rectangle {
    id: toggle

    property bool checked: false
    signal toggled(bool checked)

    implicitWidth: 36
    implicitHeight: 18
    color: checked ? Theme.primary : Theme.selection
    border.width: checked ? 0 : 1
    border.color: Theme.separator
    activeFocusOnTab: true

    Rectangle {
        width: 12
        height: 12
        anchors.verticalCenter: parent.verticalCenter
        x: toggle.checked ? parent.width - width - 3 : 3
        color: toggle.checked ? Theme.textOnColor : Theme.textSecondary

        Behavior on x { NumberAnimation { duration: 120 } }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: toggle.activeFocus
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: toggle.toggled(!toggle.checked)
    }

    Keys.onSpacePressed: toggled(!checked)
}
