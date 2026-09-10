import QtQuick
import Mtee

// Common player pinned at the bottom of the window. The foundation step draws
// its zones only: the transport arrives with the player step, and the classic
// progress bar is replaced by the waveform later on.
Panel {
    id: bar

    property string trackTitle: ""
    property string trackArtist: ""
    signal listeningViewRequested()

    Rectangle {
        id: artwork
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Theme.spacing
        width: Theme.playerHeight - 2 * Theme.spacing
        height: width
        radius: Theme.controlRadius
        color: Theme.activeSurface

        Text {
            anchors.centerIn: parent
            text: "♪"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
        }
    }

    Column {
        anchors.left: artwork.right
        anchors.leftMargin: Theme.spacing
        anchors.verticalCenter: parent.verticalCenter
        width: 220
        spacing: 2

        Text {
            text: bar.trackTitle
            color: Theme.textPrimary
            elide: Text.ElideRight
            width: parent.width
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            text: bar.trackArtist
            color: Theme.textSecondary
            elide: Text.ElideRight
            width: parent.width
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Row {
        id: transport
        anchors.centerIn: parent
        spacing: Theme.spacingSmall

        ToolButton { text: "Previous"; enabledAction: false }
        ToolButton { text: "Play"; primary: true; enabledAction: false }
        ToolButton { text: "Next"; enabledAction: false }
    }

    Rectangle {
        id: progress
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        anchors.bottomMargin: Theme.spacingSmall
        height: 4
        radius: 2
        color: Theme.activeSurface

        Rectangle {
            width: 0
            height: parent.height
            radius: parent.radius
            color: Theme.accent
        }
    }

    ToolButton {
        anchors.right: parent.right
        anchors.rightMargin: Theme.spacing
        anchors.verticalCenter: parent.verticalCenter
        text: "Listening view"
        onClicked: bar.listeningViewRequested()
    }
}
