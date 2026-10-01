import QtQuick
import Mtee

// Shuffle, Previous, Play/Pause, Next and Repeat, shared by the island and the
// fullscreen player. Active modes are drawn in the primary colour with a dot.
Row {
    id: controls

    required property var player
    property int buttonSize: 32
    property int iconSize: 18
    property int playSize: 32
    property string playObjectName: "playButton"
    property string previousObjectName: "previousButton"
    property color iconColor: Theme.textSecondary
    property color hoverColor: Theme.textPrimary
    property color activeColor: Theme.primary
    property color playColor: Theme.primary
    property color playHoverColor: Theme.primaryHover
    property color playIconColor: Theme.textOnColor
    readonly property bool willPlay: controls.player.isPlaying
        || (controls.player.status === "Loading" && !controls.player.pausePending)

    spacing: 8

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "shuffle"
        iconSize: controls.iconSize
        iconColor: controls.iconColor
        hoverColor: controls.hoverColor
        activeColor: controls.activeColor
        active: controls.player.shuffle
        showDot: controls.player.shuffle
        tip: controls.player.shuffle ? "Disable shuffle" : "Enable shuffle"
        onClicked: controls.player.toggleShuffle()
    }

    IconButton {
        objectName: controls.previousObjectName
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "previous"
        iconSize: controls.iconSize
        iconColor: controls.iconColor
        hoverColor: controls.hoverColor
        activeColor: controls.activeColor
        tip: "Previous"
        onClicked: controls.player.previous()
    }

    Rectangle {
        id: play
        objectName: controls.playObjectName
        anchors.verticalCenter: parent.verticalCenter
        width: controls.playSize
        height: controls.playSize
        radius: width / 2
        color: playMouse.containsMouse ? controls.playHoverColor : controls.playColor
        scale: playMouse.pressed ? 0.94 : 1.0

        Icon {
            anchors.centerIn: parent
            name: controls.willPlay ? "pause" : "play"
            size: Math.round(controls.playSize * 0.5)
            color: controls.playIconColor
        }

        MouseArea {
            id: playMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: controls.player.togglePlay()
        }

        HoverTip {
            visible: playMouse.containsMouse
            text: controls.player.status === "Loading"
                ? (controls.player.pausePending ? "Play when ready" : "Pause when ready")
                : controls.player.isPlaying ? "Pause (Space)" : "Play (Space)"
        }
    }

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "next"
        iconSize: controls.iconSize
        iconColor: controls.iconColor
        hoverColor: controls.hoverColor
        activeColor: controls.activeColor
        tip: "Next"
        onClicked: controls.player.next()
    }

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: controls.player.repeat === "one" ? "repeat-one" : "repeat"
        iconSize: controls.iconSize
        iconColor: controls.iconColor
        hoverColor: controls.hoverColor
        activeColor: controls.activeColor
        active: controls.player.repeat !== "off"
        showDot: controls.player.repeat !== "off"
        tip: controls.player.repeat === "off" ? "Repeat all"
            : controls.player.repeat === "all" ? "Repeat one" : "Disable repeat"
        onClicked: controls.player.cycleRepeat()
    }
}
