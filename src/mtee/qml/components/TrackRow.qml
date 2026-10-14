import QtQuick
import Mtee

// Track data stays separate from the trailing row actions.
Rectangle {
    id: row
    objectName: "trackRow"

    required property var track
    required property var columns
    required property var workspace
    property int groupIndex: 0
    property bool selected: false
    readonly property string localId: track.trackId !== undefined ? track.trackId : track.id
    readonly property bool available: track.available !== false
    property var dragTrackIds: []
    property var dragEntryIds: []
    property string dragSource: ""
    property int dragVersion: -1
    property bool dragCanAdd: false
    property bool dragPrepared: false
    property bool dragCancelled: false
    property string dragEntryId: track.entryId || ""
    signal dragStarted()
    signal dragMoved(real x, real y)
    signal dragFinished()
    Component.onDestruction: {
        if (dragPrepared) {
            dragCancelled = true
            dragFinished()
        }
    }
    // Declared first so it sits below hitArea: a click in the table margin only clears the selection.
    MouseArea {
        objectName: "trackRowMargin"
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onClicked: row.marginClicked()
    }

    // Pointer input covers the table columns only, the same span as the highlight.
    Item {
        id: hitArea
        x: row.columns.padding
        width: row.width - 2 * row.columns.padding
        height: row.height
    }
    DragHandler {
        id: trackDrag
        parent: hitArea
        target: null
        acceptedButtons: Qt.LeftButton
        enabled: row.available || row.dragEntryId.length > 0
        onTranslationChanged: {
            if (active) row.dragMoved(centroid.position.x + hitArea.x, centroid.position.y + hitArea.y)
        }
        onActiveChanged: {
            if (active) {
                row.dragCancelled = false
                row.dragStarted()
                row.dragMoved(centroid.position.x + hitArea.x, centroid.position.y + hitArea.y)
            } else {
                row.dragFinished()
                row.dragPrepared = false
            }
        }
    }
    property bool playing: false
    property bool paused: false
    property bool current: false
    property bool inPlaylist: false
    property bool separateArtist: true
    // Set by the list while it has keyboard focus: every selected row then shows the frame.
    property bool focusFrame: false
    // Neighbour rows that are selected too; they share one block frame.
    property bool selectedAbove: false
    property bool selectedBelow: false
    // Right edge of the visible table, in row coordinates; the table can scroll under it.
    property real viewportRight: width
    readonly property real frameRight: Math.min(row.width - row.columns.padding, row.viewportRight - row.columns.padding)
    // Where the trailing actions sit when the table fits: right after the last column.
    readonly property real actionsNaturalX: rowCells.x + rowCells.width + row.columns.gap
    readonly property bool hovered: mouse.containsMouse || rowHover.hovered
        || playButton.hovered || infoButton.hovered || addButton.hovered
    signal pressed(var event)
    signal leftClicked(var event)
    signal marginClicked()
    signal activated()
    signal toggleRequested()
    signal contextRequested(real x, real y)
    signal infoRequested()
    signal playlistRequested(var anchor)

    height: Theme.rowHeight
    opacity: available ? 1 : 0.55
    color: "transparent"
    Accessible.name: row.track.title + (row.track.artist.length > 0 ? " — " + row.track.artist : "")

    // Highlight and focus frame span the table columns, not the whole viewport,
    // and stop at the visible edge when the table scrolls sideways.
    Rectangle {
        x: row.columns.padding
        width: row.frameRight - row.columns.padding
        height: parent.height
        color: row.selected ? Theme.selection : row.hovered ? Theme.surface : "transparent"
    }

    // A selected row draws only its side edges; top and bottom appear at the ends of a block,
    // so a run of selected rows reads as one frame.
    Item {
        objectName: "trackFocusFrame"
        z: 1
        x: row.columns.padding
        width: row.frameRight - row.columns.padding
        height: parent.height
        readonly property bool edgeTop: !(row.selected && row.selectedAbove)
        readonly property bool edgeBottom: !(row.selected && row.selectedBelow)
        visible: row.current || (row.selected && row.focusFrame)

        Rectangle {
            x: 0; y: 0
            width: 1; height: parent.height
            color: Theme.focus
        }
        Rectangle {
            x: parent.width - 1; y: 0
            width: 1; height: parent.height
            color: Theme.focus
        }
        Rectangle {
            visible: parent.edgeTop
            x: 0; y: 0
            width: parent.width; height: 1
            color: Theme.focus
        }
        Rectangle {
            visible: parent.edgeBottom
            x: 0; y: parent.height - 1
            width: parent.width; height: 1
            color: Theme.focus
        }
    }

    MouseArea {
        id: mouse
        parent: hitArea
        anchors.fill: hitArea
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: (event) => row.pressed(event)
        onDoubleClicked: (event) => { if (event.button === Qt.LeftButton) row.activated() }
        // Positions are relative to the hit area, which starts after the table margin.
        onClicked: (event) => {
            if (event.button === Qt.RightButton)
                row.contextRequested(event.x + hitArea.x, event.y + hitArea.y)
            else
                row.leftClicked(event)
        }
    }

    HoverHandler {
        id: rowHover
        parent: hitArea
    }

    IconButton {
        id: playButton
        objectName: "trackPlayButton"
        x: row.columns.padding
        anchors.verticalCenter: parent.verticalCenter
        width: 32; height: 32
        visible: row.available && (row.hovered || row.playing)
        hoverBackground: false
        icon: row.playing && !row.paused ? "pause" : "play"
        iconSize: 14
        iconColor: row.playing ? Theme.primary : Theme.textPrimary
        hoverColor: row.playing ? Theme.primary : Theme.textPrimary
        tip: row.playing && !row.paused ? "Pause" : "Play"
        onClicked: row.playing ? row.toggleRequested() : row.activated()
    }

    Text {
        objectName: "trackNumber"
        x: row.columns.padding
        width: row.columns.playSlot
        anchors.verticalCenter: parent.verticalCenter
        visible: !playButton.visible && row.track.number !== undefined
        horizontalAlignment: Text.AlignHCenter
        text: row.track.number !== undefined ? String(row.track.number) : ""
        color: row.playing ? Theme.primary : Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
        font.features: { "tnum": 1 }
    }

    Row {
        id: rowCells
        x: row.columns.padding + row.columns.playSlot + row.columns.gap
        height: parent.height
        spacing: row.columns.gap

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
                        bpm: row.track.bpmText !== undefined ? row.track.bpmText : row.track.bpm,
                        duration: row.track.duration,
                        bitrate: row.track.bitrateText || row.track.bitrate,
                        fileCreatedAt: row.track.fileCreatedAtText,
                        fileModifiedAt: row.track.fileModifiedAtText,
                        format: row.track.format,
                        filename: row.track.filename,
                        // A count of 0 is shown as "0", so it is passed as text.
                        playCount: row.track.playCount !== undefined ? String(row.track.playCount) : "",
                        lastPlayed: row.track.lastPlayedText
                    }
                    return String(values[columnKey] || "")
                }

                width: modelData.width
                height: row.height

                CoverArt {
                    id: cover
                    visible: field.columnKey === "title" && row.columns.showArtwork
                    width: Theme.coverSize
                    height: Theme.coverSize
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    pattern: row.track.cover
                    source: row.track.coverUrl || ""
                }

                Column {
                    visible: field.columnKey === "title"
                    anchors.left: cover.visible ? cover.right : parent.left
                    anchors.leftMargin: cover.visible ? 10 : 0
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
                    camelot: row.track.keyCamelot !== undefined ? row.track.keyCamelot : row.track.key
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
    }

    // Trailing actions stay at the visible right edge while the columns scroll beneath them.
    Item {
        id: actionsBox
        x: Math.min(row.actionsNaturalX, row.viewportRight - row.columns.padding - row.columns.actions)
        width: row.columns.actions
        height: row.height

        // Opaque backing only while the buttons sit over scrolled columns.
        Rectangle {
            anchors.fill: parent
            visible: actionsBox.x < row.actionsNaturalX
            color: row.selected ? Theme.selection : row.hovered ? Theme.surface : Theme.background
        }

        Row {
            width: parent.width
            height: parent.height
            spacing: 4
            layoutDirection: Qt.RightToLeft

            IconButton {
                id: addButton
                objectName: "trackAdd_" + row.track.id
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

            TextButton {
                visible: !row.available
                anchors.verticalCenter: parent.verticalCenter
                text: "Locate"; kind: "ghost"
                onClicked: row.workspace.playlistModel.requestUI("locate", row.track.entryId, [row.track.id])
            }
            IconButton {
                objectName: "trackLike_" + row.track.id
                visible: typeof row.workspace.toggleLike === "function" && row.available
                anchors.verticalCenter: parent.verticalCenter
                icon: row.workspace.revision >= 0 && typeof row.workspace.isLiked === "function"
                    && row.workspace.isLiked(row.localId) ? "heart-filled" : "heart"
                iconSize: 16
                hoverBackground: false
                tip: "Like track"
                onClicked: row.workspace.toggleLike(row.localId)
            }
            IconButton {
                id: infoButton
                objectName: "trackInfoButton"
                anchors.verticalCenter: parent.verticalCenter
                visible: row.hovered && row.available
                hoverBackground: false
                icon: "info"
                iconSize: 18
                tip: "Edit info (Ctrl+I)"
                onClicked: row.infoRequested()
            }

        }
    }

}
