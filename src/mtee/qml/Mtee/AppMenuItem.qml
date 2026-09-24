import QtQuick
import QtQuick.Controls.Basic

// Menu entry with an optional check mark and a keyboard shortcut hint.
MenuItem {
    id: item

    property string hint: ""
    property bool mark: false

    implicitWidth: 252
    implicitHeight: 28
    padding: 0
    indicator: null

    arrow: Icon {
        x: item.width - width - 8
        anchors.verticalCenter: parent.verticalCenter
        visible: item.subMenu !== null
        name: "chevron-right"
        size: 14
        color: Theme.textSecondary
    }

    contentItem: Item {
        Icon {
            x: 8
            anchors.verticalCenter: parent.verticalCenter
            visible: item.mark
            name: "check"
            size: 14
            color: Theme.primary
        }

        Text {
            x: 30
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - hintText.implicitWidth - 24
            text: item.text
            elide: Text.ElideRight
            color: item.enabled ? Theme.textPrimary : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            id: hintText
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: item.hint
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    background: Rectangle {
        implicitWidth: 252
        implicitHeight: 28
        color: item.highlighted && item.enabled ? Theme.selection : "transparent"
    }
}
