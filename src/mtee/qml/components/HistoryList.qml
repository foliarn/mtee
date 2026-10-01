import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Recently played tracks, most recent first, with the same lines as the queue. A click on a
// cover plays the track now (the queue and its manual additions are kept); the menu adds it
// to the queue, reveals it or opens its tags. There is no drag and drop.
Item {
    id: history

    required property var workspace
    readonly property var playback: workspace.playerModel
    property int horizontalPadding: 12
    property int rightPadding: 10
    property int labelInset: 12

    function ago(iso) {
        const then = new Date(iso)
        if (isNaN(then.getTime()))
            return ""
        const seconds = Math.max(0, (Date.now() - then.getTime()) / 1000)
        if (seconds < 60)
            return "Just now"
        const minutes = Math.floor(seconds / 60)
        if (minutes < 60)
            return minutes + " min ago"
        const hours = Math.floor(minutes / 60)
        if (hours < 24)
            return hours + " hr ago"
        const startOfToday = new Date()
        startOfToday.setHours(0, 0, 0, 0)
        const days = Math.ceil((startOfToday.getTime() - then.getTime()) / 86400000)
        return days <= 1 ? "Yesterday" : days + " days ago"
    }

    ListView {
        id: list
        objectName: "historyList"
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: history.playback.hasHistoryModel ? history.playback.historyModel : history.playback.history
        ScrollBar.vertical: ThinScrollBar {}

        header: Item {
            width: list.width
            height: list.count > 0 ? 34 : 0

            SectionLabel {
                visible: list.count > 0
                x: history.labelInset
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 4
                text: "Recently played"
                font.letterSpacing: 0
                font.capitalization: Font.MixedCase
                font.pixelSize: Theme.fontSizeSecondary
                font.bold: true
            }
        }

        delegate: QueueTrackRow {
            id: item

            required property var modelData

            width: list.width
            entryId: String(modelData.historyId || "")
            rowData: modelData
            horizontalPadding: history.horizontalPadding
            rightPadding: history.rightPadding
            timeText: history.ago(modelData.playedAt || "")
            objectName: "historyRow_" + entryId
            onCoverClicked: history.playback.playHistoryEntry(entryId)
            onRowDoubleClicked: {
                if (available)
                    history.playback.playHistoryEntry(entryId)
            }
            onMenuRequested: (anchor, x, y) => {
                menu.historyId = entryId
                menu.trackId = String(rowData.trackId || rowData.id || "")
                menu.source = String(rowData.source || "")
                menu.available = available
                menu.popup(anchor, x, y)
            }
        }
    }

    Text {
        objectName: "historyEmpty"
        visible: list.count === 0
        anchors.horizontalCenter: parent.horizontalCenter
        y: 52
        text: "Nothing played yet."
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    AppMenu {
        id: menu

        property string historyId: ""
        property string trackId: ""
        property string source: ""
        property bool available: true

        AppMenuItem {
            objectName: "historyAddToQueue"
            text: "Add to queue"
            enabled: menu.available
            onTriggered: history.playback.enqueueHistoryEntry(menu.historyId)
        }
        AppMenuItem {
            objectName: "historyGoTo"
            text: menu.source.indexOf("playlist:") === 0 ? "Go to playlist" : "Go to folder"
            onTriggered: history.workspace.revealTrack(menu.trackId, menu.source)
        }
        AppMenuItem {
            objectName: "historyEditInfo"
            text: "Edit info"
            onTriggered: history.workspace.revealTrackForEdit(menu.trackId, menu.source)
        }
    }
}
