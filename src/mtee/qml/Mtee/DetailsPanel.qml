import QtQuick
import Mtee

// Metadata inspector, folded by default. The fields are read-only here: the
// editing, its Saving / Saved / Could not save states and the multiple
// selection arrive with the metadata step.
Panel {
    id: details

    property string trackTitle: ""
    property string trackArtist: ""
    property string trackGenre: ""
    property string trackBpm: ""
    property string trackKey: ""
    signal closeRequested()

    SectionLabel {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: close.left
        anchors.margins: Theme.spacing
        text: "Details"
    }

    ToolButton {
        id: close
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Theme.spacingSmall
        text: "Hide"
        onClicked: details.closeRequested()
    }

    Column {
        anchors.top: header.bottom
        anchors.topMargin: Theme.spacing
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        spacing: Theme.spacing

        Rectangle {
            width: parent.width
            height: parent.width * 0.6
            radius: Theme.controlRadius
            color: Theme.activeSurface

            Text {
                anchors.centerIn: parent
                text: "No artwork"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Repeater {
            model: [
                { "name": "Title", "value": details.trackTitle },
                { "name": "Artist", "value": details.trackArtist },
                { "name": "Genre", "value": details.trackGenre },
                { "name": "BPM", "value": details.trackBpm },
                { "name": "Key", "value": details.trackKey }
            ]

            delegate: Column {
                required property var modelData
                width: details.width - 2 * Theme.spacing
                spacing: 2

                SectionLabel {
                    width: parent.width
                    text: parent.modelData.name
                }

                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: parent.modelData.value.length > 0 ? parent.modelData.value : "—"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }
            }
        }
    }
}
