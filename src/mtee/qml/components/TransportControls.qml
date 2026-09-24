import QtQuick
import Mtee

// Shuffle, Previous, Play/Pause, Next and Repeat, shared by the island and the
// fullscreen player. Active modes are drawn in the primary colour with a dot.
Row {
    id: controls

    required property var workspace
    property int buttonSize: 32
    property int iconSize: 18
    property int playSize: 32

    spacing: 8

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "shuffle"
        iconSize: controls.iconSize
        active: controls.workspace.shuffle
        showDot: controls.workspace.shuffle
        tip: controls.workspace.shuffle ? "Disable shuffle" : "Enable shuffle"
        onClicked: controls.workspace.toggleShuffle()
    }

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: "previous"
        iconSize: controls.iconSize
        tip: "Previous"
        onClicked: controls.workspace.previous()
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
            name: controls.workspace.isPlaying ? "pause" : "play"
            size: Math.round(controls.playSize * 0.5)
            color: Theme.textOnColor
        }

        MouseArea {
            id: playMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: controls.workspace.togglePlay()
        }

        HoverTip {
            visible: playMouse.containsMouse
            text: controls.workspace.isPlaying ? "Pause (Space)" : "Play (Space)"
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
        onClicked: controls.workspace.next()
    }

    IconButton {
        anchors.verticalCenter: parent.verticalCenter
        width: controls.buttonSize
        height: controls.buttonSize
        hoverBackground: false
        icon: controls.workspace.repeat === "one" ? "repeat-one" : "repeat"
        iconSize: controls.iconSize
        active: controls.workspace.repeat !== "off"
        showDot: controls.workspace.repeat !== "off"
        tip: controls.workspace.repeat === "off" ? "Repeat all"
            : controls.workspace.repeat === "all" ? "Repeat one" : "Disable repeat"
        onClicked: controls.workspace.cycleRepeat()
    }
}
