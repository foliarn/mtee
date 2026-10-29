import QtQuick
import Mtee

// A filled red button for an action that cannot be undone.
Rectangle {
    id: danger

    property string text: ""
    property bool enabledAction: true
    signal clicked()

    implicitWidth: dangerText.implicitWidth + 28
    implicitHeight: 32
    color: dangerMouse.containsMouse && enabledAction ? Qt.lighter(Theme.danger, 1.1) : Theme.danger
    opacity: enabledAction ? 1.0 : 0.4

    Text {
        id: dangerText
        anchors.centerIn: parent
        text: danger.text
        color: Theme.textOnColor
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
        font.weight: Font.DemiBold
    }

    MouseArea {
        id: dangerMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: danger.enabledAction ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (danger.enabledAction) danger.clicked()
    }
}
