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
        active: controls.player.shuffle
        showDot: controls.player.shuffle
        tip: controls.player.shuffle ? "Disable shuffle" : "Enable shuffle"
        onClicked: controls.player.toggleShuffle()
    }

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "previous"
        iconSize: controls.iconSize
        tip: "Previous"
        onClicked: controls.player.previous()
    }

    Rectangle {
        id: play
        objectName: "playButton"
        anchors.verticalCenter: parent.verticalCenter
        width: controls.playSize
        height: controls.playSize
        color: playMouse.containsMouse ? Theme.primaryHover : Theme.primary
        scale: playMouse.pressed ? 0.94 : 1.0

        Icon {
            anchors.centerIn: parent
            name: controls.willPlay ? "pause" : "play"
            size: Math.round(controls.playSize * 0.5)
            color: Theme.textOnColor
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
        active: controls.player.repeat !== "off"
        showDot: controls.player.repeat !== "off"
        tip: controls.player.repeat === "off" ? "Repeat all"
            : controls.player.repeat === "all" ? "Repeat one" : "Disable repeat"
        onClicked: controls.player.cycleRepeat()
    }
}
