import QtQuick

// Text control. ``kind`` is primary (lime), secondary (magenta), neutral or ghost.
Rectangle {
    id: control

    property string text: ""
    property string kind: "neutral"
    property string icon: ""
    property bool enabledAction: true
    property string tip: ""
    signal clicked()

    readonly property bool filled: kind === "primary" || kind === "secondary"
    readonly property color ink: filled ? Theme.textOnColor : Theme.textPrimary

    implicitWidth: content.implicitWidth + 28
    implicitHeight: 32
    color: kind === "primary" ? (mouse.containsMouse ? Theme.primaryHover : Theme.primary)
        : kind === "secondary" ? Theme.secondary
        : kind === "neutral" ? (mouse.containsMouse ? Theme.selection : Theme.surface)
        : (mouse.containsMouse ? Theme.surface : "transparent")
    border.width: kind === "ghost" ? 1 : 0
    border.color: Theme.separator
    opacity: enabledAction ? (mouse.pressed ? 0.85 : 1.0) : 0.4
    activeFocusOnTab: enabledAction

    Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: control.activeFocus
    }

    Row {
        id: content
        anchors.centerIn: parent
        spacing: 8

        Icon {
            visible: control.icon.length > 0
            anchors.verticalCenter: parent.verticalCenter
            name: control.icon
            size: 16
            color: control.ink
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: control.text
            color: control.ink
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: control.filled ? Font.DemiBold : Font.Normal
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: control.enabledAction ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (control.enabledAction) control.clicked()
    }

    HoverTip {
        visible: control.tip.length > 0 && mouse.containsMouse
        text: control.tip
    }

    Keys.onReturnPressed: if (enabledAction) clicked()
    Keys.onSpacePressed: if (enabledAction) clicked()
}
