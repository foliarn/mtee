import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Review prototype only: all queue mutations remain in memory.
ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 800
    minimumWidth: 760
    minimumHeight: 620
    title: "MTEE — queue review"
    color: Theme.editor
    property string scene: "panel"
    property string feedback: "Illustrative queue · no audio or files are touched"
    property int draggedIndex: -1
    property int insertionIndex: -1
    property var upcoming: []
    readonly property var sample: [
        {entryId: "manual-9a", title: "Low Orbit", artist: "Velar", duration: "4:56", origin: "Added", available: true},
        {entryId: "manual-9b", title: "Low Orbit", artist: "Velar", duration: "4:56", origin: "Added", available: true},
        {entryId: "manual-8", title: "Wired", artist: "Second Signal", duration: "4:12", origin: "Added", available: true},
        {entryId: "context-2", title: "Afterlight", artist: "Northline", duration: "5:04", origin: "Night drive", available: true},
        {entryId: "context-3", title: "Last Exit", artist: "Second Signal", duration: "4:38", origin: "Night drive", available: true},
        {entryId: "manual-missing", title: "Lost Signal", artist: "Unknown artist", duration: "", origin: "Added", available: false}
    ]

    function resetQueue() {
        trackMenu.close()
        removeMenu.close()
        upcoming = scene === "empty" ? [] : sample.map(item => Object.assign({}, item))
        draggedIndex = -1
        insertionIndex = -1
        feedback = "Illustrative queue · no audio or files are touched"
    }
    function removeEntry(entryId) {
        upcoming = upcoming.filter(item => item.entryId !== entryId)
        feedback = "Removed one occurrence from the preview"
    }
    function moveEntry(entryId, beforeId) {
        let next = upcoming.slice()
        const source = next.findIndex(item => item.entryId === entryId)
        if (source < 0) return
        const item = next.splice(source, 1)[0]
        const target = beforeId === "" ? next.length : next.findIndex(row => row.entryId === beforeId)
        if (target < 0) return
        next.splice(target, 0, item)
        upcoming = next
        feedback = "Queue order changed in this preview"
    }
    onSceneChanged: {
        resetQueue()
        if (scene === "drag") { draggedIndex = 1; insertionIndex = 4 }
        if (scene === "track-menu") Qt.callLater(() => trackMenu.popup(180, 180))
        if (scene === "queue-menu") {
            removeMenu.entryId = "manual-9b"
            Qt.callLater(() => removeMenu.popup(970, 240))
        }
    }
    Component.onCompleted: resetQueue()

    Rectangle {
        anchors.fill: parent
        color: Theme.editor
    }
    Rectangle {
        id: rail
        width: 72
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        color: Theme.sidebar
        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 28
            spacing: 28
            Text { text: "M"; color: Theme.primary; font.pixelSize: 24; font.bold: true }
            Text { text: "E"; color: Theme.textSecondary; font.pixelSize: 19; font.bold: true }
            Text { text: "P"; color: Theme.textSecondary; font.pixelSize: 19; font.bold: true }
        }
    }
    Column {
        anchors.left: rail.right
        anchors.right: queueCard.left
        anchors.top: parent.top
        anchors.bottom: footer.top
        anchors.margins: 26
        spacing: 18
        Text { text: scene === "fullscreen" ? "Fullscreen player" : "Night drive"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 28; font.bold: true }
        Text { text: "Select a track, then use its context menu"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
        Repeater {
            model: ["Control (Original Mix)", "Wired", "Low Orbit", "Afterlight"]
            delegate: Rectangle {
                required property string modelData
                required property int index
                width: parent.width
                height: 52
                radius: 6
                color: index === 0 ? Theme.surface : "transparent"
                Text { anchors.left: parent.left; anchors.leftMargin: 18; anchors.verticalCenter: parent.verticalCenter; text: (index + 1) + "     " + modelData; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14 }
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.RightButton; onClicked: trackMenu.popup() }
            }
        }
        Text { text: "Right-click a track to preview Add to queue"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }
    Rectangle {
        id: queueCard
        width: scene === "fullscreen" ? Math.min(510, root.width * 0.45) : Math.min(390, root.width * 0.38)
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: footer.top
        color: Theme.sidebar
        Rectangle { width: 1; anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; color: Theme.separator }
        Column {
            anchors.fill: parent
            anchors.topMargin: 24
            spacing: 10
            Text { x: 20; text: "Queue"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 21; font.bold: true }
            Text { x: 20; text: "Now playing"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
            Rectangle {
                width: parent.width; height: 58; color: Theme.surface
                Text { x: 20; anchors.verticalCenter: parent.verticalCenter; text: "PLAYING    Control (Original Mix)\n                  Northline"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 13; lineHeight: 1.25 }
            }
            Text { x: 20; text: "UP NEXT · " + root.upcoming.length; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
            Item {
                width: parent.width
                height: Math.max(0, queueCard.height - 244)
                clip: true
                ListView {
                    id: queueList
                    anchors.fill: parent
                    model: root.upcoming
                    spacing: 0
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Item {
                        id: row
                        required property var modelData
                        required property int index
                        width: queueList.width
                        height: 64
                        readonly property bool dragged: root.draggedIndex === index
                        Rectangle { anchors.fill: parent; color: row.dragged ? Theme.surface : mouse.containsMouse ? Theme.surface : "transparent"; opacity: row.dragged ? 0.72 : 1 }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 3; color: Theme.primary; visible: root.draggedIndex >= 0 && root.insertionIndex === row.index }
                        Text { x: 13; anchors.verticalCenter: parent.verticalCenter; text: "||"; color: Theme.textMuted; font.pixelSize: 14 }
                        Column {
                            x: 38; width: parent.width - 126; anchors.verticalCenter: parent.verticalCenter; spacing: 3
                            Text { width: parent.width; text: row.modelData.title; elide: Text.ElideRight; color: row.modelData.available ? Theme.textPrimary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
                            Text { width: parent.width; text: row.modelData.artist + " · " + row.modelData.origin; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                        }
                        Text { anchors.right: parent.right; anchors.rightMargin: 16; anchors.verticalCenter: parent.verticalCenter; text: row.modelData.available ? row.modelData.duration : "Unavailable"; color: row.modelData.available ? Theme.textMuted : Theme.danger; font.family: Theme.fontFamily; font.pixelSize: 11 }
                        MouseArea {
                            id: mouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            property real startY: 0
                            onPressed: event => {
                                if (event.button === Qt.RightButton) { removeMenu.entryId = row.modelData.entryId; removeMenu.popup(); return }
                                startY = event.y
                            }
                            onPositionChanged: event => {
                                if (!(event.buttons & Qt.LeftButton) || Math.abs(event.y - startY) < 8 && root.draggedIndex < 0) return
                                root.draggedIndex = row.index
                                const point = row.mapToItem(queueList.contentItem, event.x, event.y)
                                root.insertionIndex = Math.max(0, Math.min(root.upcoming.length, Math.round(point.y / row.height)))
                            }
                            onReleased: event => {
                                if (root.draggedIndex >= 0) {
                                    const sourceId = row.modelData.entryId
                                    const target = root.upcoming[root.insertionIndex]
                                    root.moveEntry(sourceId, target ? target.entryId : "")
                                    root.draggedIndex = -1
                                    root.insertionIndex = -1
                                }
                            }
                            onCanceled: { root.draggedIndex = -1; root.insertionIndex = -1 }
                            onDoubleClicked: root.feedback = "Double-click would play this occurrence"
                        }
                    }
                    footer: Rectangle { width: queueList.width; height: root.draggedIndex >= 0 && root.insertionIndex === root.upcoming.length ? 3 : 0; color: Theme.primary }
                }
                Text { anchors.centerIn: parent; visible: root.upcoming.length === 0; text: "Nothing next"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
            }
            Text { x: 20; text: "History"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
            Text { x: 20; text: "Previous track · Night drive"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
        }
    }
    Rectangle {
        id: footer
        height: 80
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        color: Theme.surface
        Text { x: 24; anchors.verticalCenter: parent.verticalCenter; text: "PREV       PLAY       NEXT       Control (Original Mix)"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
        Text { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: root.feedback; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
    }
    AppMenu {
        id: trackMenu
        AppMenuItem { text: "Play" }
        AppMenuItem { text: "Add to queue"; onTriggered: { let next = root.upcoming.slice(); next.unshift({entryId: "preview-" + Date.now(), title: "Control (Original Mix)", artist: "Northline", duration: "3:48", origin: "Added", available: true}); root.upcoming = next; root.feedback = "Added to queue preview" } }
        AppMenuItem { text: "Add to playlist…" }
    }
    AppMenu {
        id: removeMenu
        property string entryId: ""
        AppMenuItem { text: "Remove from queue"; onTriggered: root.removeEntry(removeMenu.entryId) }
    }
    Shortcut { sequence: "Escape"; onActivated: { root.draggedIndex = -1; root.insertionIndex = -1 } }
}
