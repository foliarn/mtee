import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The playback queue: the playing track stays in view, then "Next in queue" (manual
// additions) and "Next from: <source>" (the rest of the context). A click on a cover plays
// that occurrence; a held row can be moved; a right click or the "…" button opens the menu
// of the occurrence. Shared by the fullscreen card and the right panel.
Item {
    id: queue

    required property var workspace
    readonly property var playback: workspace.playerModel
    property int horizontalPadding: 6
    property int rightPadding: 14
    property int labelInset: 0
    // True in the fullscreen player, where an unconsumed wheel would change the page.
    property bool wheelGuard: false
    property string listObjectName: "queueList"
    property string dragEntryId: ""
    property string dropBeforeId: ""
    property bool dragActive: false
    property int dragRevision: -1

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

    function playRow(row) {
        list.forceActiveFocus()
        if (row.current)
            queue.playback.togglePlay()
        else if (row.entryId.length > 0)
            queue.playback.playEntry(row.entryId)
    }

    // The playing track stays in view above the scrolling list.
    Column {
        id: nowPlaying
        objectName: "queueNowPlaying"
        width: parent.width

        SectionLabel {
            x: queue.labelInset
            text: "Now playing"
            height: 34
            verticalAlignment: Text.AlignVCenter
        }

        QueueTrackRow {
            id: playingRow
            visible: queue.playback.playingId.length > 0
            width: parent.width
            height: visible ? 56 : 0
            horizontalPadding: queue.horizontalPadding
            rightPadding: queue.rightPadding
            rowData: Object.assign({source: queue.playback.playingSource,
                                    trackId: queue.playback.playingId}, queue.playback.playingTrack)
            entryId: queue.playback.currentEntryId
            current: true
            playing: queue.playback.isPlaying
            onCoverClicked: queue.playRow(playingRow)
            onRowDoubleClicked: queue.playback.togglePlay()
            onMenuRequested: (anchor, x, y) => queue.openMenu(entryId, String(rowData.trackId || ""),
                String(rowData.source || ""), true, anchor, x, y)
        }
    }

    ListView {
        id: list
        objectName: queue.listObjectName
        anchors.top: nowPlaying.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: !queue.dragActive
        model: queue.playback.hasQueueModel ? queue.playback.upcomingQueueModel : queue.playback.upNext
        section.property: "queueGroup"
        section.criteria: ViewSection.FullString
        ScrollBar.vertical: ThinScrollBar {}

        // Escape cancels a drag. The window shortcut that leaves fullscreen would win,
        // so the list claims the key while a drag is under way.
        Keys.onShortcutOverride: (event) => {
            if (queue.dragActive && event.key === Qt.Key_Escape)
                event.accepted = true
        }
        Keys.onEscapePressed: queue.cancelDrag()

        section.delegate: Item {
            required property string section

            objectName: "queueSection_" + section
            width: list.width
            height: 34

            Text {
                x: queue.labelInset
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                text: parent.section === "next" ? "Next in queue"
                    : "Next from: " + queue.playback.playingSourceTitle
                elide: Text.ElideRight
                width: parent.width - queue.labelInset * 2
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.bold: true
            }
        }

        delegate: QueueTrackRow {
            id: item

            required property var modelData
            required property int index
            property real pressY: 0

            width: list.width
            rowData: modelData
            horizontalPadding: queue.horizontalPadding
            rightPadding: queue.rightPadding
            dragging: queue.dragActive && queue.dragEntryId === entryId
            dropBefore: queue.dragActive && queue.dropBeforeId === entryId
            onCoverClicked: queue.playRow(item)
            onRowDoubleClicked: queue.playRow(item)
            onMenuRequested: (anchor, x, y) => queue.openMenu(entryId, String(rowData.trackId || rowData.id || ""),
                String(rowData.source || ""), false, anchor, x, y)
            onPressedAt: (row, x, y) => {
                list.forceActiveFocus()
                pressY = y
                if (entryId.length > 0) {
                    queue.dragEntryId = entryId
                    queue.dragRevision = queue.playback.queueRevision
                }
            }
            onMovedTo: (row, x, y, buttons) => {
                if (!(buttons & Qt.LeftButton) || queue.dragEntryId !== entryId)
                    return
                if (!queue.dragActive && Math.abs(y - pressY) < 8)
                    return
                queue.dragActive = true
                const point = item.mapToItem(list.contentItem, x, y)
                const targetIndex = list.indexAt(point.x, point.y)
                if (targetIndex < 0) {
                    queue.dropBeforeId = ""
                    return
                }
                const target = list.itemAtIndex(targetIndex)
                if (!target)
                    return
                if (point.y < target.y + target.height / 2) {
                    queue.dropBeforeId = target.entryId
                } else {
                    const following = list.itemAtIndex(targetIndex + 1)
                    queue.dropBeforeId = following ? following.entryId : ""
                }
            }
            onReleased: {
                const source = queue.dragEntryId
                const before = queue.dropBeforeId
                const shouldMove = queue.dragActive && source.length > 0
                queue.cancelDrag()
                if (shouldMove)
                    queue.playback.moveQueueEntry(source, before)
            }
            onCanceled: queue.cancelDrag()
        }

        footer: Item {
            width: list.width
            height: queue.dragActive && queue.dropBeforeId === "" ? 3 : 0

            Rectangle {
                anchors.fill: parent
                color: Theme.primary
            }
        }
    }

    Text {
        objectName: "queueEmpty"
        visible: list.count === 0 && queue.playback.playingId.length > 0
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
        enabled: queue.wheelGuard
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
            onTriggered: queue.playback.removeQueueEntry(rowMenu.entryId)
        }
        AppMenuItem {
            objectName: "queueGoTo"
            text: rowMenu.source.indexOf("playlist:") === 0 ? "Go to playlist" : "Go to folder"
            onTriggered: queue.workspace.revealTrack(rowMenu.trackId, rowMenu.source)
        }
        AppMenuItem {
            objectName: "queueEditInfo"
            text: "Edit info"
            onTriggered: queue.workspace.revealTrackForEdit(rowMenu.trackId, rowMenu.source)
        }
    }
}
