import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Queue of the fullscreen player: the playing track, then "Next in queue" (manual
// additions) and "Next from: <source>" (the rest of the context), without history.
// A click on a cover plays that occurrence; a held row can be moved; a right click or
// the "…" button opens the menu of the occurrence.
FullscreenCard {
    id: card

    required property var workspace
    readonly property var playback: workspace.playerModel
    property string dragEntryId: ""
    property string dropBeforeId: ""
    property bool dragActive: false
    property int dragRevision: -1
    property int previewHoverRow: -1  // review captures only

    objectName: "fullscreenQueueCard"
    heading: "Queue"

    function cancelDrag() {
        dragActive = false
        dragEntryId = ""
        dropBeforeId = ""
        dragRevision = -1
    }

    function openMenu(entryId, trackId, source, current, anchor, x, y) {
        rowMenu.entryId = entryId
        rowMenu.trackId = trackId
        rowMenu.source = source
        rowMenu.current = current
        rowMenu.popup(anchor, x, y)
    }

    component QueueRow: Item {
        id: row

        required property var rowData
        property string entryId: String(rowData.entryId || "")
        property bool current: false
        property int position: -1
        readonly property bool available: rowData.available !== false
        readonly property bool hovered: rowMouse.containsMouse || coverMouse.containsMouse
            || moreMouse.containsMouse || (card.previewHoverRow >= 0 && card.previewHoverRow === position)

        objectName: current ? "queueCurrentRow" : "queueRow_" + entryId
        width: list.width
        height: 56

        Rectangle {
            anchors.fill: parent
            anchors.rightMargin: 8
            color: card.dragActive && card.dragEntryId === row.entryId ? Theme.selection
                : row.hovered ? Theme.selection : "transparent"
            opacity: row.available ? 1 : 0.6
        }

        Rectangle {
            visible: card.dragActive && card.dropBeforeId === row.entryId && !row.current
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 3
            color: Theme.primary
        }

        MouseArea {
            id: rowMouse
            property real pressY: 0

            anchors.fill: parent
            hoverEnabled: true
            preventStealing: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onPressed: (event) => {
                list.forceActiveFocus()
                if (event.button === Qt.RightButton) {
                    card.openMenu(row.entryId, String(row.rowData.trackId || row.rowData.id || ""),
                                  String(row.rowData.source || ""), row.current, row, event.x, event.y)
                    return
                }
                pressY = event.y
                if (!row.current && row.entryId.length > 0) {
                    card.dragEntryId = row.entryId
                    card.dragRevision = card.playback.queueRevision
                }
            }
            onPositionChanged: (event) => {
                if (!(event.buttons & Qt.LeftButton) || row.current || card.dragEntryId !== row.entryId)
                    return
                if (!card.dragActive && Math.abs(event.y - pressY) < 8)
                    return
                card.dragActive = true
                const point = row.mapToItem(list.contentItem, event.x, event.y)
                const targetIndex = list.indexAt(point.x, point.y)
                if (targetIndex < 0) {
                    card.dropBeforeId = ""
                    return
                }
                const target = list.itemAtIndex(targetIndex)
                if (!target)
                    return
                if (point.y < target.y + target.height / 2) {
                    card.dropBeforeId = target.entryId
                } else {
                    const following = list.itemAtIndex(targetIndex + 1)
                    card.dropBeforeId = following ? following.entryId : ""
                }
            }
            onReleased: {
                const source = card.dragEntryId
                const before = card.dropBeforeId
                const shouldMove = card.dragActive && source.length > 0
                card.cancelDrag()
                if (shouldMove)
                    card.playback.moveQueueEntry(source, before)
            }
            onCanceled: card.cancelDrag()
            onDoubleClicked: {
                if (row.current)
                    card.playback.togglePlay()
                else if (row.entryId.length > 0)
                    card.playback.playEntry(row.entryId)
            }
        }

        CoverArt {
            id: cover
            x: 6
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.coverSize + 4
            height: width
            opacity: row.available ? 1 : 0.5
            pattern: row.rowData.cover !== undefined ? row.rowData.cover : -1
            source: row.rowData.coverUrl || ""

            Rectangle {
                anchors.fill: parent
                color: "#000000"
                opacity: row.available && (row.current || row.hovered) ? 0.45 : 0

                Behavior on opacity { NumberAnimation { duration: 120 } }
            }

            Icon {
                objectName: "queueCoverIcon"
                anchors.centerIn: parent
                name: row.current && card.playback.isPlaying ? "pause" : "play"
                size: 18
                color: "#FFFFFF"
                opacity: row.available && (row.current || row.hovered) ? 1 : 0

                Behavior on opacity { NumberAnimation { duration: 120 } }
            }

            MouseArea {
                id: coverMouse
                objectName: "queueCoverButton"
                anchors.fill: parent
                hoverEnabled: true
                enabled: row.available
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    list.forceActiveFocus()
                    if (row.current)
                        card.playback.togglePlay()
                    else if (row.entryId.length > 0)
                        card.playback.playEntry(row.entryId)
                }
            }
        }

        Column {
            anchors.left: cover.right
            anchors.leftMargin: 12
            anchors.right: moreButton.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                objectName: "queueRowTitle"
                width: parent.width
                text: row.rowData.title || row.rowData.filename || "Unknown track"
                elide: Text.ElideRight
                color: row.current ? Theme.primary : row.available ? Theme.textPrimary : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: row.available ? (row.rowData.artist || "Unknown artist") : "Unavailable"
                elide: Text.ElideRight
                color: row.available ? Theme.textSecondary : Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Item {
            id: moreButton
            objectName: "queueRowMore"
            anchors.right: parent.right
            anchors.rightMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            width: 28
            height: 28

            Icon {
                anchors.centerIn: parent
                name: "more"
                size: 18
                color: moreMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                opacity: row.hovered ? 1 : 0
            }

            MouseArea {
                id: moreMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: card.openMenu(row.entryId, String(row.rowData.trackId || row.rowData.id || ""),
                                         String(row.rowData.source || ""), row.current, moreButton, 0, 28)
            }
        }
    }

    // The playing track stays in view above the scrolling list.
    Column {
        id: nowPlaying
        objectName: "queueNowPlaying"
        width: parent.width

        SectionLabel {
            text: "Now playing"
            height: 34
            verticalAlignment: Text.AlignVCenter
        }

        QueueRow {
            visible: card.playback.playingId.length > 0
            height: visible ? 56 : 0
            rowData: Object.assign({source: card.playback.playingSource,
                                    trackId: card.playback.playingId}, card.playback.playingTrack)
            entryId: card.playback.currentEntryId
            current: true
        }
    }

    ListView {
        id: list
        objectName: "fullscreenQueueList"
        anchors.top: nowPlaying.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: !card.dragActive
        model: card.playback.hasQueueModel ? card.playback.upcomingQueueModel : card.playback.upNext
        section.property: "queueGroup"
        section.criteria: ViewSection.FullString
        ScrollBar.vertical: ThinScrollBar {}

        // Escape cancels a drag. The window shortcut that leaves fullscreen would win,
        // so the list claims the key while a drag is under way.
        Keys.onShortcutOverride: (event) => {
            if (card.dragActive && event.key === Qt.Key_Escape)
                event.accepted = true
        }
        Keys.onEscapePressed: card.cancelDrag()

        section.delegate: Item {
            required property string section

            objectName: "queueSection_" + section
            width: list.width
            height: 34

            Text {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                text: parent.section === "next" ? "Next in queue" : "Next from: " + card.playback.playingSourceTitle
                elide: Text.ElideRight
                width: parent.width
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.bold: true
            }
        }

        delegate: QueueRow {
            required property var modelData
            required property int index

            rowData: modelData
            position: index
        }

        footer: Item {
            width: list.width
            height: card.dragActive && card.dropBeforeId === "" ? 3 : 0

            Rectangle {
                anchors.fill: parent
                color: Theme.primary
            }
        }
    }

    Text {
        objectName: "queueEmpty"
        visible: list.count === 0 && card.playback.playingId.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        y: nowPlaying.height + 16
        text: "Nothing next."
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    // The list consumes the wheel, at its bounds too: it never changes the page.
    MouseArea {
        objectName: "queueWheelGuard"
        anchors.fill: list
        acceptedButtons: Qt.NoButton
        onWheel: (wheel) => {
            const max = Math.max(0, list.contentHeight - list.height)
            list.contentY = Math.max(0, Math.min(max, list.contentY - wheel.angleDelta.y * 0.5))
            wheel.accepted = true
        }
    }

    AppMenu {
        id: rowMenu

        property string entryId: ""
        property string trackId: ""
        property string source: ""
        property bool current: false

        AppMenuItem {
            objectName: "queueRemove"
            text: "Remove from queue"
            visible: !rowMenu.current
            height: visible ? implicitHeight : 0
            onTriggered: card.playback.removeQueueEntry(rowMenu.entryId)
        }
        AppMenuItem {
            objectName: "queueGoTo"
            text: rowMenu.source.indexOf("playlist:") === 0 ? "Go to playlist" : "Go to folder"
            onTriggered: card.workspace.revealTrack(rowMenu.trackId, rowMenu.source)
        }
        AppMenuItem {
            objectName: "queueEditInfo"
            text: "Edit info"
            onTriggered: card.workspace.revealTrackForEdit(rowMenu.trackId, rowMenu.source)
        }
    }

}
