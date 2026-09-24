import QtQuick

// Square icon control. ``active`` marks a toggled state in the primary colour.
Rectangle {
    id: control

    property string icon: ""
    property int iconSize: 20
    property color iconColor: Theme.textSecondary
    property color hoverColor: Theme.textPrimary
    property color activeColor: Theme.primary
    property bool active: false
    property bool showDot: false
    property bool hoverBackground: true
    property string tip: ""
    property bool enabledAction: true
    readonly property bool hovered: mouse.containsMouse
    signal clicked()

    implicitWidth: 32
    implicitHeight: 32
    color: hoverBackground && mouse.containsMouse && enabledAction
        ? (mouse.pressed ? Theme.selection : Theme.surface) : "transparent"
    opacity: enabledAction ? 1.0 : 0.4

    Icon {
        anchors.centerIn: parent
        name: control.icon
        size: control.iconSize
        color: control.active ? control.activeColor
            : mouse.containsMouse && control.enabledAction ? control.hoverColor
            : control.iconColor
    }

    Rectangle {
        visible: control.showDot
        width: 4
        height: 4
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 1
        color: control.activeColor
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton
        cursorShape: control.enabledAction ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (control.enabledAction) control.clicked()
    }

    HoverTip {
        visible: control.tip.length > 0 && mouse.containsMouse
        text: control.tip
    }
}
