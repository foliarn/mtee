import QtQuick
import Mtee

// One Spotify-style line: number, cover, title over artist, album, genre, BPM,
// Camelot key, duration, then Edit info and Add to playlist on hover.
Rectangle {
    id: row

    required property var track
    required property var columns
    property bool selected: false
    property bool playing: false
    property bool paused: false
    property bool current: false
    property bool inPlaylist: false
    readonly property bool hovered: mouse.containsMouse
    signal pressed(var event)
    signal activated()
    signal toggleRequested()
    signal contextRequested(real x, real y)
    signal infoRequested()
    signal playlistRequested(var anchor)

    height: Theme.rowHeight
    color: selected ? Theme.selection : hovered ? Theme.surface : "transparent"

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: row.current
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: (event) => row.pressed(event)
        onDoubleClicked: (event) => { if (event.button === Qt.LeftButton) row.activated() }
        onClicked: (event) => { if (event.button === Qt.RightButton) row.contextRequested(event.x, event.y) }
    }

    Row {
        x: row.columns.padding
        height: parent.height
        spacing: row.columns.gap

        Item {
            width: row.columns.number
            height: parent.height

            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: !row.hovered && !(row.playing && !row.paused)
                text: row.track.number
                color: row.playing ? Theme.primary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.features: { "tnum": 1 }
            }

            IconButton {
                anchors.right: parent.right
                anchors.rightMargin: -8
                anchors.verticalCenter: parent.verticalCenter
                visible: row.hovered || (row.playing && !row.paused)
                hoverBackground: false
                icon: row.playing && !row.paused ? (row.hovered ? "pause" : "play") : "play"
                iconSize: 14
                iconColor: row.playing ? Theme.primary : Theme.textPrimary
                hoverColor: row.playing ? Theme.primary : Theme.textPrimary
                onClicked: row.playing ? row.toggleRequested() : row.activated()
            }
        }

        Item {
            width: row.columns.title
            height: parent.height

            CoverArt {
                id: cover
                width: Theme.coverSize
                height: Theme.coverSize
                anchors.verticalCenter: parent.verticalCenter
                pattern: row.track.cover
            }

            Column {
                anchors.left: cover.right
                anchors.leftMargin: 12
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Text {
                    width: parent.width
                    text: row.track.title
                    elide: Text.ElideRight
                    color: row.playing ? Theme.primary : Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    width: parent.width
                    text: row.track.artist.length > 0 ? row.track.artist : "Unknown artist"
                    elide: Text.ElideRight
                    color: row.track.artist.length > 0
                        ? (row.hovered || row.selected ? Theme.textPrimary : Theme.textSecondary)
                        : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }

        Cell {
            width: row.columns.album
            visible: row.columns.album > 0
            text: row.track.album
        }

        Cell {
            width: row.columns.genre
            visible: row.columns.genre > 0
            text: row.track.genre
        }

        Cell {
            width: row.columns.bpm
            text: row.track.bpm
            alignRight: true
        }

        Item {
            width: row.columns.key
            height: parent.height
            KeyBadge {
                anchors.centerIn: parent
                key: row.track.key
            }
        }

        Cell {
            width: row.columns.duration
            text: row.track.duration
            alignRight: true
        }

        Row {
            width: row.columns.actions
            height: parent.height
            spacing: 4
            layoutDirection: Qt.RightToLeft

            IconButton {
                id: addButton
                anchors.verticalCenter: parent.verticalCenter
                hoverBackground: false
                icon: row.inPlaylist ? "check" : "add-playlist"
                iconSize: 18
                iconColor: row.inPlaylist ? Theme.secondary
                    : row.hovered || row.selected ? Theme.textSecondary : Theme.textMuted
                hoverColor: Theme.secondary
                tip: "Add to playlist"
                onClicked: row.playlistRequested(addButton)
            }

            IconButton {
                anchors.verticalCenter: parent.verticalCenter
                visible: row.hovered
                hoverBackground: false
                icon: "info"
                iconSize: 18
                tip: "Edit info (Ctrl+I)"
                onClicked: row.infoRequested()
            }
        }
    }

    component Cell: Item {
        id: cell
        property string text: ""
        property bool alignRight: false
        height: row.height

        Text {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            horizontalAlignment: cell.alignRight ? Text.AlignRight : Text.AlignLeft
            text: cell.text.length > 0 ? cell.text : "—"
            elide: Text.ElideRight
            color: cell.text.length > 0 && cell.text !== "—"
                ? (row.hovered || row.selected ? Theme.textPrimary : Theme.textSecondary)
                : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.features: { "tnum": 1 }
        }
    }
}
