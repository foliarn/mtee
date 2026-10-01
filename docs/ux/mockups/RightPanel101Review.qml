import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Review prototype only (plan 101.1): the right panel with Info, Queue and History.
// Every list lives in memory; nothing touches audio, files or the database.
ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 800
    minimumWidth: 760
    minimumHeight: 560
    title: "MTEE — right panel review"
    color: Theme.editor

    property string scene: "queue"
    property string tab: "queue"
    property string feedback: "Illustrative panel · no audio or files are touched"
    property int previewHoverRow: -1
    property string dragId: ""
    property string dropBeforeId: ""
    property bool dragActive: false
    property string playingId: "now"
    property bool playing: true
    property var upcoming: []
    property var history: []

    readonly property var nowTrack: ({id: "now", title: "Control (Original Mix)", artist: "Northline", cover: 3, available: true})
    readonly property var queueSample: [
        {id: "q1", title: "Low Orbit", artist: "Velar", cover: 0, available: true, group: "next"},
        {id: "q2", title: "Low Orbit", artist: "Velar", cover: 0, available: true, group: "next"},
        {id: "q3", title: "Wired", artist: "Second Signal", cover: 1, available: true, group: "next"},
        {id: "q4", title: "Afterlight", artist: "Northline", cover: 2, available: true, group: "context"},
        {id: "q5", title: "Last Exit", artist: "Second Signal", cover: 5, available: true, group: "context"},
        {id: "q6", title: "Lost Signal", artist: "Unknown artist", cover: -1, available: false, group: "context"},
        {id: "q7", title: "Glass Harbor", artist: "Mira Vale", cover: 6, available: true, group: "context"},
        {id: "q8", title: "Night Shift", artist: "Velar", cover: 7, available: true, group: "context"},
        {id: "q9", title: "Pale Fire", artist: "Northline", cover: 4, available: true, group: "context"}
    ]
    readonly property var historySample: [
        {id: "h1", title: "Afterlight", artist: "Northline", cover: 2, available: true, ago: "3 min ago"},
        {id: "h2", title: "Wired", artist: "Second Signal", cover: 1, available: true, ago: "9 min ago"},
        {id: "h3", title: "Glass Harbor", artist: "Mira Vale", cover: 6, available: true, ago: "14 min ago"},
        {id: "h4", title: "Lost Signal", artist: "Unknown artist", cover: -1, available: false, ago: "22 min ago"},
        {id: "h5", title: "Low Orbit", artist: "Velar", cover: 0, available: true, ago: "31 min ago"},
        {id: "h6", title: "Night Shift", artist: "Velar", cover: 7, available: true, ago: "45 min ago"},
        {id: "h7", title: "Pale Fire", artist: "Northline", cover: 4, available: true, ago: "1 hr ago"},
        {id: "h8", title: "Low Orbit", artist: "Velar", cover: 0, available: true, ago: "Yesterday"},
        {id: "h9", title: "Last Exit", artist: "Second Signal", cover: 5, available: true, ago: "Yesterday"},
        {id: "h10", title: "Deep Water", artist: "Mira Vale", cover: 3, available: true, ago: "Yesterday"},
        {id: "h11", title: "Static Bloom", artist: "Kesh", cover: 1, available: true, ago: "Yesterday"},
        {id: "h12", title: "Harbor Lights", artist: "Kesh", cover: 2, available: true, ago: "2 days ago"}
    ]

    function reset() {
        rowMenu.close()
        upcoming = scene === "queue-empty" ? [] : queueSample.map(item => Object.assign({}, item))
        history = scene === "history-empty" ? [] : historySample.map(item => Object.assign({}, item))
        dragId = ""; dropBeforeId = ""; dragActive = false
        previewHoverRow = scene === "queue-hover" ? 2 : scene === "history" || scene === "history-times" ? -1 : -1
        tab = scene.indexOf("history") === 0 ? "history" : scene === "info" ? "info" : "queue"
        feedback = "Illustrative panel · no audio or files are touched"
    }
    function removeEntry(id) { upcoming = upcoming.filter(item => item.id !== id); feedback = "Removed one occurrence from the preview" }
    function moveEntry(id, beforeId) {
        let next = upcoming.slice()
        const source = next.findIndex(item => item.id === id)
        if (source < 0) return
        const item = next.splice(source, 1)[0]
        const target = beforeId === "" ? next.length : next.findIndex(row => row.id === beforeId)
        if (target < 0) return
        next.splice(target, 0, item)
        upcoming = next
        feedback = "Queue order changed in this preview"
    }
    function playHistory(id) { feedback = "Would play this track now; the queue stays as it is"; }
    onSceneChanged: {
        reset()
        if (scene === "queue-drag") { dragId = "q3"; dragActive = true; dropBeforeId = "q5" }
        if (scene === "queue-menu") Qt.callLater(() => openRowMenu("queue", "q2", 0, 0, 0, 0))
        if (scene === "history-menu") Qt.callLater(() => openRowMenu("history", "h3", 0, 0, 0, 0))
    }
    Component.onCompleted: reset()

    property var menuAnchor: null
    function openRowMenu(kind, id, a, b, x, y) {
        rowMenu.kind = kind
        rowMenu.rowId = id
        rowMenu.popup(panel.x + 120, scene === "queue-menu" ? 330 : 380)
    }

    // Stand-in for the editor area.
    Column {
        anchors.left: parent.left
        anchors.right: panel.left
        anchors.top: parent.top
        anchors.bottom: footer.top
        anchors.margins: 26
        spacing: 14
        Text { text: "Night drive"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 28; font.bold: true }
        Text { text: "Editor area (not part of this review)"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
        Repeater {
            model: 6
            delegate: Rectangle { required property int index; width: parent.width; height: 44; radius: 6; color: index === 0 ? Theme.surface : "transparent"
                Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: (index + 1) + "     Track " + (index + 1); color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 14 } }
        }
    }

    Rectangle {
        id: panel
        width: Theme.rightPanelWidth
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: footer.top
        color: Theme.sidebar

        Rectangle { width: 1; height: parent.height; color: Theme.separator; opacity: 0.6 }

        Item {
            id: header
            x: 1
            width: parent.width - 1
            height: Theme.tabHeight
            Row {
                x: 10
                height: parent.height
                Repeater {
                    model: [{key: "info", label: "Info"}, {key: "queue", label: "Queue"}, {key: "history", label: "History"}]
                    delegate: Item {
                        id: tabItem
                        required property var modelData
                        readonly property bool current: root.tab === modelData.key
                        width: tabLabel.implicitWidth + 20
                        height: header.height
                        Text {
                            id: tabLabel
                            anchors.centerIn: parent
                            text: tabItem.modelData.label.toUpperCase()
                            color: tabItem.current || tabMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeCaption
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.1
                        }
                        Rectangle { visible: tabItem.current; anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; width: tabLabel.implicitWidth; height: 2; color: Theme.primary }
                        MouseArea { id: tabMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.tab = tabItem.modelData.key }
                    }
                }
            }
            IconButton { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter; width: 26; height: 26; icon: "close"; iconSize: 16; tip: "Close panel" }
        }

        // Shared row: used by Queue, History and the playing track.
        component PanelRow: Item {
            id: row
            required property var rowData
            property string kind: "queue"
            property bool current: false
            property int position: -1
            property bool withTime: false
            readonly property bool available: rowData.available !== false
            readonly property bool hovered: rowMouse.containsMouse || coverMouse.containsMouse || moreMouse.containsMouse
                || (kind === "queue" && position >= 0 && root.previewHoverRow === position)
            width: parent ? parent.width : 0
            height: 56

            Rectangle {
                anchors.fill: parent
                anchors.leftMargin: 4
                anchors.rightMargin: 4
                radius: 4
                color: root.dragActive && root.dragId === row.rowData.id ? Theme.selection : row.hovered ? Theme.selection : "transparent"
                opacity: row.available ? 1 : 0.6
            }
            Rectangle {
                visible: root.dragActive && row.kind === "queue" && root.dropBeforeId === row.rowData.id && !row.current
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: 3; color: Theme.primary
            }
            MouseArea {
                id: rowMouse
                property real pressY: 0
                anchors.fill: parent
                hoverEnabled: true
                preventStealing: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onPressed: event => {
                    if (event.button === Qt.RightButton) { root.openRowMenu(row.kind, row.rowData.id, 0, 0, 0, 0); return }
                    pressY = event.y
                    if (row.kind === "queue" && !row.current) root.dragId = row.rowData.id
                }
                onPositionChanged: event => {
                    if (row.kind !== "queue" || !(event.buttons & Qt.LeftButton) || row.current || root.dragId !== row.rowData.id) return
                    if (!root.dragActive && Math.abs(event.y - pressY) < 8) return
                    root.dragActive = true
                    const point = row.mapToItem(queueList.contentItem, event.x, event.y)
                    const index = queueList.indexAt(point.x, point.y)
                    if (index < 0) { root.dropBeforeId = ""; return }
                    const target = queueList.itemAtIndex(index)
                    if (!target) return
                    if (point.y < target.y + target.height / 2) root.dropBeforeId = target.rowData.id
                    else { const next = queueList.itemAtIndex(index + 1); root.dropBeforeId = next ? next.rowData.id : "" }
                }
                onReleased: {
                    const source = root.dragId, before = root.dropBeforeId, move = root.dragActive && source.length > 0
                    root.dragId = ""; root.dropBeforeId = ""; root.dragActive = false
                    if (move) root.moveEntry(source, before)
                }
                onCanceled: { root.dragId = ""; root.dropBeforeId = ""; root.dragActive = false }
                onDoubleClicked: if (!row.current) root.feedback = row.kind === "queue" ? "Double-click would play this occurrence" : "Double-click would play this track now"
            }
            CoverArt {
                id: cover
                x: 12
                anchors.verticalCenter: parent.verticalCenter
                width: 44; height: 44
                opacity: row.available ? 1 : 0.5
                pattern: row.rowData.cover
                Rectangle { anchors.fill: parent; color: "#000000"; opacity: row.available && (row.current || row.hovered) ? 0.45 : 0; Behavior on opacity { NumberAnimation { duration: 120 } } }
                Icon {
                    anchors.centerIn: parent
                    name: row.current && root.playing ? "pause" : "play"
                    size: 18; color: "#FFFFFF"
                    opacity: row.available && (row.current || row.hovered) ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                }
                MouseArea {
                    id: coverMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: row.available
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (row.current) root.playing = !root.playing
                        else root.feedback = row.kind === "queue" ? "Cover click would play this occurrence" : "Cover click would play this track now"
                    }
                }
            }
            Column {
                anchors.left: cover.right; anchors.leftMargin: 10
                anchors.right: right.left; anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text { width: parent.width; text: row.rowData.title; elide: Text.ElideRight; color: row.current ? Theme.primary : row.available ? Theme.textPrimary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody }
                Text { width: parent.width; text: row.available ? row.rowData.artist : "Unavailable"; elide: Text.ElideRight; color: row.available ? Theme.textSecondary : Theme.danger; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
            }
            Item {
                id: right
                anchors.right: parent.right; anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                width: row.withTime ? 74 : 28
                height: 28
                Text {
                    visible: row.withTime
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    text: row.rowData.ago || ""
                    color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
                    opacity: row.hovered ? 0 : 1
                }
                Icon { anchors.right: parent.right; anchors.rightMargin: 5; anchors.verticalCenter: parent.verticalCenter; name: "more"; size: 18; color: moreMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary; opacity: row.hovered && !row.current ? 1 : (row.hovered ? 1 : 0) }
                MouseArea { id: moreMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.openRowMenu(row.kind, row.rowData.id, 0, 0, 0, 0) }
            }
        }

        // Queue tab
        Item {
            visible: root.tab === "queue"
            anchors.top: header.bottom; anchors.bottom: parent.bottom
            anchors.left: parent.left; anchors.leftMargin: 1; anchors.right: parent.right
            Column {
                id: nowPlaying
                width: parent.width
                SectionLabel { x: 12; text: "Now playing"; height: 34; verticalAlignment: Text.AlignVCenter }
                PanelRow { rowData: root.nowTrack; kind: "queue"; current: true }
            }
            ListView {
                id: queueList
                anchors.top: nowPlaying.bottom; anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                interactive: !root.dragActive
                model: root.upcoming
                section.property: "group"
                section.criteria: ViewSection.FullString
                ScrollBar.vertical: ThinScrollBar {}
                section.delegate: Item {
                    required property string section
                    width: queueList.width; height: 34
                    Text { x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 4
                        text: parent.section === "next" ? "Next in queue" : "Next from: Deep Focus"; elide: Text.ElideRight
                        color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary; font.bold: true }
                }
                delegate: PanelRow { required property var modelData; required property int index; rowData: modelData; position: index; kind: "queue" }
                footer: Item { width: queueList.width; height: root.dragActive && root.dropBeforeId === "" ? 3 : 0; Rectangle { anchors.fill: parent; color: Theme.primary } }
            }
            Text { visible: root.upcoming.length === 0; anchors.horizontalCenter: parent.horizontalCenter; y: nowPlaying.height + 16; text: "Nothing next."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }
        }

        // History tab
        Item {
            visible: root.tab === "history"
            anchors.top: header.bottom; anchors.bottom: parent.bottom
            anchors.left: parent.left; anchors.leftMargin: 1; anchors.right: parent.right
            ListView {
                id: historyList
                anchors.fill: parent
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: root.history
                ScrollBar.vertical: ThinScrollBar {}
                header: Item { width: historyList.width; height: 34
                    SectionLabel { x: 12; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 4; visible: root.history.length > 0; text: "Recently played"; font.letterSpacing: 0; font.capitalization: Font.MixedCase; font.pixelSize: Theme.fontSizeSecondary; font.bold: true } }
                delegate: PanelRow { required property var modelData; required property int index; rowData: modelData; position: index; kind: "history"; withTime: root.scene === "history-times" }
            }
            Text { visible: root.history.length === 0; anchors.horizontalCenter: parent.horizontalCenter; y: 52; text: "Nothing played yet."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }
        }

        // Info tab: a flat placeholder, unchanged by this plan.
        Rectangle { visible: root.tab === "info"; anchors.top: header.bottom; anchors.bottom: parent.bottom; anchors.left: parent.left; anchors.leftMargin: 1; anchors.right: parent.right; color: Theme.sidebar
            Text { anchors.centerIn: parent; text: "Info panel (unchanged)"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 } }
    }

    Rectangle {
        id: footer
        height: 80
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        color: Theme.surface
        Text { x: 24; anchors.verticalCenter: parent.verticalCenter; text: "Control (Original Mix) · Northline"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
        Text { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: root.feedback; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
    }

    AppMenu {
        id: rowMenu
        property string kind: "queue"
        property string rowId: ""
        implicitWidth: 220
        AppMenuItem { text: "Remove from queue"; visible: rowMenu.kind === "queue"; height: visible ? implicitHeight : 0; onTriggered: root.removeEntry(rowMenu.rowId) }
        AppMenuItem { text: "Add to queue"; visible: rowMenu.kind === "history"; height: visible ? implicitHeight : 0; onTriggered: root.feedback = "Added to the end of the manual queue (preview)" }
        AppMenuItem { text: rowMenu.kind === "queue" ? "Go to playlist" : "Go to folder"; onTriggered: root.feedback = "Would reveal the track in its source" }
        AppMenuItem { text: "Edit info"; onTriggered: root.feedback = "Would open the metadata editor" }
    }
    Shortcut { sequence: "Escape"; onActivated: { root.dragId = ""; root.dropBeforeId = ""; root.dragActive = false } }
}
