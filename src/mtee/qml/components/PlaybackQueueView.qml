import QtQuick
import QtQuick.Controls.Basic
import Mtee

// One virtualized scroll surface for the queue, current track and history.
ListView {
    id: queueView
    required property var player
    required property var workspace
    property int bottomInset: 0
    property string dragEntryId: ""
    property string dropBeforeId: ""
    property int dragRevision: -1
    property bool dragActive: false
    property string removeEntryId: ""
    objectName: "playbackQueueView"
    clip: true
    spacing: 0
    boundsBehavior: Flickable.StopAtBounds
    model: player.hasQueueModel ? player.upcomingQueueModel : player.upNext
    ScrollBar.vertical: ThinScrollBar {}

    function cancelDrag() {
        dragActive = false
        dragEntryId = ""
        dropBeforeId = ""
        dragRevision = -1
    }

    header: Column {
        width: queueView.width
        spacing: 6
        Item { width: 1; height: 12 }
        SectionLabel { x: 16; text: "Now playing" }
        Rectangle {
            width: parent.width
            height: queueView.player.playingId.length > 0 ? 56 : 0
            visible: height > 0
            color: Theme.surface
            Text {
                x: 16; width: parent.width - 32; anchors.verticalCenter: parent.verticalCenter
                text: queueView.player.playingTrack.title || ""
                elide: Text.ElideRight; color: Theme.primary
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary
            }
        }
        Item { width: 1; height: 10 }
        SectionLabel { x: 16; text: "Up next" }
        Item { width: 1; height: 6 }
    }

    delegate: Item {
        id: row
        required property var modelData
        required property int index
        readonly property string entryId: String(modelData.entryId || "")
        readonly property bool available: modelData.available !== false
        objectName: "queueEntry_" + entryId
        width: queueView.width
        height: 52
        Rectangle {
            anchors.fill: parent
            color: queueView.dragEntryId === row.entryId && queueView.dragActive
                ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            height: 3; color: Theme.primary
            visible: queueView.dragActive && queueView.dropBeforeId === row.entryId
        }
        Text {
            x: 10; width: 25; anchors.verticalCenter: parent.verticalCenter
            text: "||"; horizontalAlignment: Text.AlignHCenter
            color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13
            visible: row.entryId.length > 0
        }
        Column {
            x: 43; width: parent.width - 125; anchors.verticalCenter: parent.verticalCenter; spacing: 2
            Text {
                width: parent.width; text: row.modelData.title || row.modelData.filename || "Unknown track"
                elide: Text.ElideRight; color: row.available ? Theme.textPrimary : Theme.textMuted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary
            }
            Text {
                width: parent.width
                text: (row.modelData.artist || "Unknown artist") + (row.modelData.origin === "manual" ? " · Added" : "")
                elide: Text.ElideRight; color: Theme.textSecondary
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
            }
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            text: row.available ? (row.modelData.duration || "") : "Unavailable"
            color: row.available ? Theme.textMuted : Theme.danger
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
        MouseArea {
            id: handle
            x: 0; width: 34; height: parent.height
            acceptedButtons: Qt.LeftButton
            preventStealing: true
            enabled: row.entryId.length > 0
            property real pressY: 0
            onPressed: event => {
                pressY = event.y
                queueView.dragEntryId = row.entryId
                queueView.dragRevision = queueView.player.queueRevision
            }
            onPositionChanged: event => {
                if (!(event.buttons & Qt.LeftButton)) return
                if (!queueView.dragActive && Math.abs(event.y - pressY) < 8) return
                queueView.dragActive = true
                const point = handle.mapToItem(queueView.contentItem, event.x, event.y)
                const targetIndex = queueView.indexAt(point.x, point.y)
                if (targetIndex < 0) { queueView.dropBeforeId = ""; return }
                const target = queueView.itemAtIndex(targetIndex)
                if (!target) return
                if (point.y < target.y + target.height / 2) queueView.dropBeforeId = target.entryId
                else {
                    const following = queueView.itemAtIndex(targetIndex + 1)
                    queueView.dropBeforeId = following ? following.entryId : ""
                }
            }
            onReleased: {
                const source = queueView.dragEntryId
                const before = queueView.dropBeforeId
                const shouldMove = queueView.dragActive && source.length > 0
                queueView.cancelDrag()
                if (shouldMove) queueView.player.moveQueueEntry(source, before)
            }
            onCanceled: queueView.cancelDrag()
        }
        MouseArea {
            id: rowMouse
            x: 34; width: parent.width - 34; height: parent.height
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: event => {
                if (event.button === Qt.RightButton && row.entryId.length > 0) {
                    queueView.removeEntryId = row.entryId
                    removeMenu.popup(row, event.x + rowMouse.x, event.y)
                }
            }
            onDoubleClicked: {
                if (row.entryId.length > 0) queueView.player.playEntry(row.entryId)
                else queueView.workspace.playTrack(row.modelData.id, "folder:" + (row.modelData.folder || ""))
            }
        }
    }

    footer: Column {
        width: queueView.width
        spacing: 8
        Rectangle {
            width: parent.width; height: queueView.dragActive && queueView.dropBeforeId === "" ? 3 : 0
            color: Theme.primary
        }
        Text {
            x: 16; visible: queueView.count === 0
            text: "Nothing next."; color: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
        Item { width: 1; height: 12 }
        SectionLabel { x: 16; text: "History" }
        Repeater {
            model: queueView.player.history
            delegate: Text {
                required property var modelData
                x: 16; width: queueView.width - 32; height: 32
                text: modelData.title || "Unknown track"; elide: Text.ElideRight
                color: Theme.textSecondary; font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
        Item { width: 1; height: queueView.bottomInset + 20 }
    }

    AppMenu {
        id: removeMenu
        AppMenuItem {
            objectName: "removeQueueAction"
            text: "Remove from queue"
            onTriggered: queueView.player.removeQueueEntry(queueView.removeEntryId)
        }
    }
    Shortcut { sequence: "Escape"; enabled: queueView.dragActive; onActivated: queueView.cancelDrag() }
}
