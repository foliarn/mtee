import QtQuick
import Mtee

// Flat control with a distinct hover, pressed and keyboard focus state.
Rectangle {
    id: control

    property string text: ""
    property bool primary: false
    property bool enabledAction: true
    signal clicked()

    implicitWidth: label.implicitWidth + Theme.spacingLarge
    implicitHeight: 30
    radius: Theme.controlRadius
    color: !control.enabledAction
        ? Qt.rgba(0.11, 0.17, 0.25, 0.6)
        : mouse.pressed
            ? Theme.accent
            : control.primary || mouse.containsMouse
                ? Theme.activeSurface
                : "transparent"
    border.width: 1
    border.color: control.activeFocus ? Theme.accent : Theme.border
    opacity: control.enabledAction ? 1.0 : 0.5
    activeFocusOnTab: control.enabledAction

    Text {
        id: label
        anchors.centerIn: parent
        text: control.text
        color: mouse.pressed ? Theme.background : Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeBody
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: control.enabledAction
        cursorShape: Qt.PointingHandCursor
        onClicked: control.clicked()
    }

    Keys.onReturnPressed: if (control.enabledAction) control.clicked()
    Keys.onSpacePressed: if (control.enabledAction) control.clicked()
}
