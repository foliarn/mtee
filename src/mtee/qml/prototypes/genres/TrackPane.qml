import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../../components" as Components

ColumnLayout {
    id: pane
    spacing: 12
    property string collection: "House"
    property string reviewScene: "house"
    property bool compact: false
    property bool tagging: reviewScene !== "seed"
    property string brush: collection === "Jump Up" ? "Drum & Bass › Jump Up" : "House › Deep"
    property string extraBrush: ""
    property int filterMode: 0
    property string status: ""
    property var selected: []
    property var history: []
    property bool filterEditor: false
    property int dataRevision: 0
    signal manageRequested()
    signal createRequested()
    signal playRequested(string title)
    readonly property var brushes: ["House › Deep", "House › Minimal", "Dubstep › Deep", "UK Garage › Speed Garage", "UK Garage › Bassline", "Drum & Bass › Jump Up"].concat(extraBrush ? [extraBrush] : [])
    readonly property int matches: {
        pane.dataRevision
        let total = 0
        for (let i = 0; i < tracks.count; ++i) if (matchesFilter(tracks.get(i))) ++total
        return total
    }
    function matchesFilter(row) {
        const assigned = row.genres.split(" | ")
        if (filterMode === 1) return !assigned.includes(brush)
        if (filterMode === 2) return !row.genres.includes("›")
        if (filterMode === 3) return assigned.includes("UK Garage › Speed Garage") && assigned.includes("UK Garage › Bassline")
        if (filterMode === 4) return assigned.includes("UK Garage › Speed Garage") || assigned.includes("UK Garage › Bassline")
        if (filterMode === 5) return (!assigned.includes(brush) || !row.genres.includes("›")) && !assigned.includes("UK Garage › Bassline")
        return true
    }
    function refresh() {
        for (let i = 0; i < tracks.count; ++i) tracks.setProperty(i, "shown", matchesFilter(tracks.get(i)))
    }
    function resetRows() {
        tracks.clear()
        const genres = collection === "Jump Up" ? ["Drum & Bass › Jump Up", "Drum & Bass › Jump Up", "Drum & Bass", "Drum & Bass › Jump Up | Drum & Bass › Minimal", "Drum & Bass › Liquid"] : collection === "Weekend selections" ? ["UK Garage › Speed Garage | UK Garage › Bassline", "UK Garage › Speed Garage", "UK Garage › Bassline", "House", "House | Drum & Bass › Jump Up"] : ["House", "House › Deep", "House › Deep | House › Minimal", "House | Drum & Bass › Jump Up", ""]
        const titles = ["Side streets", "Under the glass", "Parallel lines", "Night crossing", "Open horizon"]
        const artists = ["North Window", "Glass Shapes", "Fable & Isla", "Koda", "Sunday Static"]
        for (let i = 0; i < titles.length; ++i) tracks.append({title: titles[i], artist: artists[i], genres: genres[i], bpm: collection === "Jump Up" ? "174.00" : i === 4 ? "" : String(124 + i) + ".00", shown: true})
        selected = []; history = []; status = ""
        filterMode = reviewScene === "filters" ? 5 : reviewScene === "retained" ? 1 : 0
        refresh()
        if (reviewScene === "retained") { tracks.setProperty(0, "genres", brush); status = "1 row retained until Refresh results" }
        if (reviewScene === "saving") status = "Saving…"
        if (reviewScene === "error") status = "Could not save · your choice is kept for retry"
        if (reviewScene === "multi") selected = [0, 2]
        dataRevision++
    }
    function toggleSelection(index, modifiers) {
        let next = selected.slice()
        if (modifiers & Qt.ShiftModifier && next.length) {
            const start = next[next.length - 1]
            for (let i = Math.min(start, index); i <= Math.max(start, index); ++i) if (!next.includes(i)) next.push(i)
        } else if (modifiers & Qt.ControlModifier) {
            next = next.includes(index) ? next.filter(i => i !== index) : next.concat([index])
        } else next = [index]
        selected = next
    }
    function setMembership(indices, enabled) {
        let before = []
        for (const i of indices) {
            const previous = tracks.get(i).genres
            if (!enabled && !previous.split(" | ").includes(brush)) continue
            before.push({index: i, genres: previous})
            let values = previous ? previous.split(" | ") : []
            const family = brush.split(" › ")[0]
            if (enabled) {
                values = values.filter(g => g !== family && g !== brush)
                values.push(brush)
            } else {
                values = values.filter(g => g !== brush)
                if (!values.some(g => g === family || g.startsWith(family + " › "))) values.push(family)
            }
            tracks.setProperty(i, "genres", values.join(" | "))
        }
        history = history.concat([before])
        dataRevision++
        status = "Saved (preview) · Undo available"
    }
    function undo() {
        if (!history.length) return
        const before = history[history.length - 1]
        for (const row of before) tracks.setProperty(row.index, "genres", row.genres)
        history = history.slice(0, -1)
        dataRevision++
        status = "Undone (preview)"
    }
    onCollectionChanged: resetRows()
    onReviewSceneChanged: resetRows()
    onFilterModeChanged: { if (reviewScene !== "retained") refresh() }
    onBrushChanged: refresh()
    Component.onCompleted: resetRows()
    ListModel { id: tracks }

    component Label: Text {
        color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12
        elide: Text.ElideRight
    }
    component Action: Button {
        id: action
        property bool accent: false
        implicitHeight: 32; leftPadding: 10; rightPadding: 10
        contentItem: Label { text: action.text; color: action.accent ? Theme.textOnColor : action.enabled ? Theme.textPrimary : Theme.textMuted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: action.accent ? Theme.primary : action.hovered ? Theme.selection : Theme.surface; border.color: action.activeFocus ? Theme.focus : Theme.separator }
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: pane.compact ? pane.collection : pane.collection === "Weekend selections" ? "Playlist tracks" : "Folder tracks"; font.bold: true; Layout.fillWidth: true }
        Action { text: "Tagging"; accent: pane.tagging; onClicked: pane.tagging = !pane.tagging }
        Action { text: "Filters"; onClicked: pane.filterEditor = !pane.filterEditor }
    }
    Rectangle {
        visible: pane.tagging
        Layout.fillWidth: true; implicitHeight: brushBody.height + 24
        color: Theme.sidebar; border.color: Theme.separator
        ColumnLayout {
            id: brushBody; x: 12; y: 12; width: parent.width - 24; spacing: 10
            Label { text: "BRUSH / GENRES"; color: Theme.primary; font.letterSpacing: 1.4; font.pixelSize: 11 }
            ReviewCombo {
                id: picker
                Layout.fillWidth: true; model: pane.brushes; editable: true
                currentIndex: Math.max(0, pane.brushes.indexOf(pane.brush))
                onActivated: pane.brush = currentText
            }
            RowLayout {
                Layout.fillWidth: true
                Action { text: "+ Create genre…"; onClicked: pane.createRequested() }
                Item { Layout.fillWidth: true }
                Action { text: "Manage…"; onClicked: pane.manageRequested() }
            }
            Label { text: "Checkbox = this genre only. Click a row to select; Play to listen."; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; color: Theme.textSecondary }
        }
    }
    Flow {
        Layout.fillWidth: true; spacing: 8
        Components.FilterChip { text: "Without brush genre"; checked: pane.filterMode === 1; onToggled: pane.filterMode = checked ? 0 : 1 }
        Components.FilterChip { text: "No subgenre"; checked: pane.filterMode === 2; onToggled: pane.filterMode = checked ? 0 : 2 }
        Components.FilterChip { text: "All / Any…"; checked: pane.filterEditor; onToggled: pane.filterEditor = !pane.filterEditor }
    }
    Rectangle {
        visible: pane.filterEditor || pane.reviewScene === "filters"
        Layout.fillWidth: true; implicitHeight: filterBody.height + 24
        color: Theme.surface; border.color: Theme.separator
        ColumnLayout {
            id: filterBody; x: 12; y: 12; width: parent.width - 24; spacing: 8
            Label { text: "COMBINE FILTERS"; font.pixelSize: 11; color: Theme.textSecondary; font.letterSpacing: 1 }
            ReviewCombo {
                Layout.fillWidth: true
                model: ["All: Speed Garage + Bassline", "Any: Speed Garage + Bassline", "All: (Any: without brush / no subgenre) + exclude Bassline"]
                currentIndex: pane.filterMode >= 3 ? pane.filterMode - 3 : 0
                onActivated: pane.filterMode = currentIndex + 3
            }
            Label { text: pane.collection === "Jump Up" ? "Exclude Drum & Bass is unavailable in this context." : "Exclusions apply inside this folder or playlist."; color: Theme.textSecondary; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone }
            RowLayout {
                Action { text: "Reset"; onClicked: pane.filterMode = 0 }
                Action { text: "Save filter…"; onClicked: pane.status = "Sample filter ready in Settings (preview)" }
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Label { text: pane.matches + " matching · " + pane.selected.length + " selected"; Layout.fillWidth: true; color: Theme.textSecondary }
        Action { text: "Refresh results"; onClicked: { pane.refresh(); pane.status = "Results refreshed" } }
    }
    RowLayout {
        visible: pane.selected.length > 0 && pane.tagging
        Layout.fillWidth: true
        Action { text: "Add to " + pane.selected.length; onClicked: pane.setMembership(pane.selected, true) }
        Action { text: "Remove from " + pane.selected.length; onClicked: pane.setMembership(pane.selected, false) }
        Action { text: "Undo"; enabled: pane.history.length > 0; onClicked: pane.undo() }
    }
    Label {
        visible: pane.status !== ""; text: pane.status
        color: pane.reviewScene === "error" ? Theme.danger : Theme.textSecondary
        Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone
    }
    Action { visible: pane.reviewScene === "error"; text: "Retry (preview)"; onClicked: pane.status = "Saved (preview)" }
    RowLayout {
        Layout.fillWidth: true
        Label { text: "TITLE / ARTIST"; color: Theme.textMuted; font.pixelSize: 10; Layout.fillWidth: true }
        Label { text: "ANALYSIS BPM"; color: Theme.textMuted; font.pixelSize: 10; Layout.preferredWidth: 85 }
    }
    ListView {
        id: list
        Layout.fillWidth: true; Layout.fillHeight: true
        model: tracks; clip: true; spacing: 1
        ScrollBar.vertical: ScrollBar {}
        WheelScrollHandler { flickable: list }
        delegate: Rectangle {
            id: trackRow
            required property int index
            required property string title
            required property string artist
            required property string genres
            required property string bpm
            required property bool shown
            readonly property bool retained: shown && !pane.matchesFilter({genres: genres})
            width: list.width; height: shown ? (pane.compact ? 110 : 88) : 0
            visible: shown
            color: pane.selected.includes(index) ? Theme.selection : index % 2 ? Theme.sidebar : Theme.editor
            opacity: retained ? 0.55 : 1
            MouseArea { anchors.fill: parent; onClicked: mouse => { pane.toggleSelection(trackRow.index, mouse.modifiers); list.forceActiveFocus() } }
            RowLayout {
                anchors.fill: parent; anchors.margins: 8; spacing: 10
                CheckBox {
                    id: membership
                    visible: pane.tagging
                    checked: trackRow.genres.split(" | ").includes(pane.brush)
                    onClicked: pane.setMembership([trackRow.index], checked)
                    Accessible.name: "Assign " + pane.brush + " to " + trackRow.title
                    indicator: Rectangle {
                        x: 6; anchors.verticalCenter: parent.verticalCenter
                        width: 20; height: 20
                        color: membership.checked ? Theme.primary : Theme.surface
                        border.color: membership.activeFocus ? Theme.focus : membership.checked ? Theme.primary : Theme.textMuted
                        Text { anchors.centerIn: parent; text: membership.checked ? "x" : ""; color: Theme.textOnColor; font.pixelSize: 16 }
                    }
                }
                Action { text: "▶"; onClicked: pane.playRequested(trackRow.title + " · " + trackRow.artist) }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Label { text: trackRow.title; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
                    Label { text: trackRow.artist; color: Theme.textSecondary; Layout.fillWidth: true }
                    Label { text: "MTEE genres: " + (trackRow.genres || "None"); color: Theme.textSecondary; Layout.fillWidth: true; wrapMode: Text.WordWrap; elide: Text.ElideNone; font.pixelSize: 11 }
                    Label { visible: trackRow.retained; text: "No longer matches · retained until refresh"; color: Theme.warning; Layout.fillWidth: true; font.pixelSize: 10 }
                }
                Label { text: trackRow.bpm || "—"; Layout.preferredWidth: pane.compact ? 45 : 85; horizontalAlignment: Text.AlignRight }
            }
        }
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Z && event.modifiers & Qt.ControlModifier) { pane.undo(); event.accepted = true }
        }
    }
    Label { text: "File Genre: separate metadata field · Seed folder: " + pane.collection; color: Theme.textMuted; font.pixelSize: 11; Layout.fillWidth: true }
}
