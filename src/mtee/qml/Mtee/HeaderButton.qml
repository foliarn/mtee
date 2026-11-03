import QtQuick

// A square icon button of the frame: the header and the bars use it, so they look alike
// (plan 130). ``badge`` shows a small count when above zero; ``active`` tints the icon.
Item {
    id: button

    property string icon: ""
    property int iconSize: 20
    property int badge: 0
    property bool active: false
    property bool enabledAction: true
    property string tip: ""
    readonly property bool hovered: inner.hovered
    signal clicked()

    implicitWidth: Theme.frameSize
    implicitHeight: Theme.frameSize

    IconButton {
        id: inner
        objectName: "headerButtonInner"
        anchors.fill: parent
        anchors.margins: 4
        radius: Theme.radiusControl
        icon: button.icon
        iconSize: button.iconSize
        active: button.active
        tip: button.tip
        enabledAction: button.enabledAction
        onClicked: button.clicked()
    }

    Rectangle {
        objectName: "headerButtonBadge"
        visible: button.badge > 0
        x: parent.width - width - 2
        y: 2
        width: Math.max(16, badgeText.implicitWidth + 8)
        height: 16
        radius: Theme.radiusChip
        color: Theme.secondary

        Text {
            id: badgeText
            anchors.centerIn: parent
            text: button.badge > 99 ? "99+" : String(button.badge)
            color: Theme.textOnColor
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.DemiBold
        }
    }
}
