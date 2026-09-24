import QtQuick
import Mtee

// One Spotify-style line: number, cover, title over artist, album, genre, BPM,
// Camelot key, duration, then Edit info and Add to playlist on hover.
Rectangle {
    id: row
    objectName: "trackRow"

    required property var track
    required property var columns
    required property var workspace
    property int groupIndex: 0
    property bool selected: false
    property bool playing: false
    property bool paused: false
    property bool current: false
    property bool inPlaylist: false
    property bool separateArtist: true
    property var dragTrackIds: []
    property bool dragReady: false
    readonly property bool hovered: mouse.containsMouse || rowHover.hovered
        || playButton.hovered || infoButton.hovered || addButton.hovered
    signal pressed(var event)
    signal activated()
    signal toggleRequested()
    signal contextRequested(real x, real y)
    signal infoRequested()
    signal playlistRequested(var anchor)

    height: Theme.rowHeight
    color: selected ? Theme.selection : hovered ? Theme.surface : "transparent"

    Drag.active: dragReady
    Drag.source: row
    Drag.supportedActions: Qt.MoveAction
    Drag.mimeData: ({ "application/x-mtee-track-ids": JSON.stringify(dragTrackIds) })

    DragHandler {
        id: dragHandler
        target: null
        acceptedButtons: Qt.LeftButton

        onActiveChanged: {
            if (!active) {
                row.dragReady = false
                return
            }
            row.workspace.setActiveGroup(row.groupIndex)
            if (row.workspace.selectedIds.indexOf(row.track.id) < 0)
                row.workspace.selectTrack(row.track.id, "single", [])
            row.dragTrackIds = row.workspace.selectedIds.slice()
            row.dragReady = row.dragTrackIds.length > 0
        }
    }

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

    HoverHandler {
        id: rowHover
    }

    Row {
        id: rowCells
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
                id: playButton
                objectName: "trackPlayButton"
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

        Repeater {
            model: row.columns.items

            delegate: Item {
                id: field
                required property var modelData
                readonly property string columnKey: modelData.key
                readonly property string displayText: {
                    const values = {
                        artist: row.track.artist,
                        album: row.track.album,
                        genre: row.track.genre,
                        bpm: row.track.bpm,
                        duration: row.track.duration,
                        bitrate: row.track.bitrateText || row.track.bitrate,
                        format: row.track.format,
                        filename: row.track.filename
                    }
                    return String(values[columnKey] || "")
                }

                width: modelData.width
                height: row.height

                CoverArt {
                    id: cover
                    visible: field.columnKey === "title"
                    width: Theme.coverSize
                    height: Theme.coverSize
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    pattern: row.track.cover
                    source: row.track.coverUrl || ""
                }

                Column {
                    visible: field.columnKey === "title"
                    anchors.left: cover.right
                    anchors.leftMargin: 10
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
                        visible: !row.separateArtist
                        width: parent.width
                        text: row.track.artist.length > 0 ? row.track.artist : "Unknown artist"
                        elide: Text.ElideRight
                        color: row.track.artist.length > 0 ? Theme.textSecondary : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }

                KeyBadge {
                    visible: field.columnKey === "key"
                    anchors.centerIn: parent
                    key: row.track.key
                }

                Text {
                    visible: field.columnKey !== "title" && field.columnKey !== "key"
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width
                    horizontalAlignment: field.columnKey === "bpm" || field.columnKey === "duration"
                        ? Text.AlignRight : Text.AlignLeft
                    text: field.displayText.length > 0 ? field.displayText : "—"
                    elide: Text.ElideRight
                    color: field.displayText.length > 0
                        ? (row.hovered || row.selected ? Theme.textPrimary : Theme.textSecondary)
                        : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    font.features: { "tnum": 1 }
                }
            }
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
                id: infoButton
                objectName: "trackInfoButton"
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

}
