import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Now playing, the queue captured when playback started, and the history.
Item {
    id: queue

    required property var workspace
    property int bottomInset: 0

    objectName: "queuePanel"

    Flickable {
        id: scroller
        anchors.fill: parent
        contentHeight: body.implicitHeight + 24 + queue.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: body
            y: 16
            width: scroller.width
            spacing: 6

            SectionLabel { x: 16; text: "Now playing" }

            QueueRow {
                visible: queue.workspace.playingId.length > 0
                track: queue.workspace.playingTrack
                playing: true
            }

            Item { width: 1; height: 10 }

            SectionLabel {
                x: 16
                text: "Next from " + queue.workspace.playingSourceTitle + (queue.workspace.shuffle ? " · shuffled" : "")
            }

            Repeater {
                model: queue.workspace.upNext
                delegate: QueueRow {
                    required property var modelData
                    track: modelData
                    source: queue.workspace.playingSource
                }
            }

            Text {
                x: 16
                visible: queue.workspace.upNext.length === 0
                text: queue.workspace.repeat === "all" ? "The queue starts again after this track." : "Nothing next."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Item { width: 1; height: 10 }

            SectionLabel { x: 16; text: "History" }

            Repeater {
                model: queue.workspace.history
                delegate: QueueRow {
                    required property var modelData
                    track: modelData
                    dimmed: true
                }
            }
        }
    }

    component QueueRow: Rectangle {
        id: row

        property var track: ({})
        property bool playing: false
        property bool dimmed: false
        property string source: ""

        width: body.width
        height: 48
        color: rowMouse.containsMouse ? Theme.surface : "transparent"

        CoverArt {
            id: art
            x: 16
            anchors.verticalCenter: parent.verticalCenter
            width: 36
            height: 36
            pattern: row.track.cover !== undefined ? row.track.cover : -1
            opacity: row.dimmed ? 0.6 : 1
        }

        Column {
            anchors.left: art.right
            anchors.leftMargin: 10
            anchors.right: time.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 1

            Text {
                width: parent.width
                text: row.track.title || ""
                elide: Text.ElideRight
                color: row.playing ? Theme.primary : row.dimmed ? Theme.textSecondary : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Text {
                width: parent.width
                text: row.track.artist && row.track.artist.length > 0 ? row.track.artist : "Unknown artist"
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Text {
            id: time
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: row.track.duration || ""
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            onDoubleClicked: {
                if (!row.playing)
                    queue.workspace.playTrack(row.track.id, row.source.length > 0 ? row.source : "folder:" + row.track.folder)
            }
        }
    }
}
