import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Review prototype only (plan 101.1): the compact "Add to playlist" menu.
// Toggles and filters act on in-memory arrays; no playlist or file is touched.
ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 800
    minimumWidth: 760
    minimumHeight: 560
    title: "MTEE — Add to playlist review"
    color: Theme.editor

    property string scene: "menu"
    property string feedback: "Illustrative menu · no playlist is touched"
    property string query: ""
    property var saved: ({})     // playlist id -> "all" | "partial"
    property bool noPlaylists: false

    readonly property var sample: [
        {id: "p1", name: "Deep Focus", count: 42, cover: 3, updated: "2026-09-30"},
        {id: "p2", name: "Night drive", count: 18, cover: 0, updated: "2026-09-28"},
        {id: "p3", name: "Gym", count: 64, cover: 2, updated: "2026-09-25"},
        {id: "p4", name: "Sunday morning", count: 12, cover: 5, updated: "2026-09-20"},
        {id: "p5", name: "Deep house essentials", count: 90, cover: 1, updated: "2026-09-18"},
        {id: "p6", name: "Road trip 2025", count: 120, cover: 7, updated: "2026-08-02"},
        {id: "p7", name: "Ambient / Study", count: 33, cover: 6, updated: "2026-07-14"},
        {id: "p8", name: "Liked from radio", count: 7, cover: 4, updated: "2026-06-01"}
    ]
    readonly property var visibleChoices: {
        if (noPlaylists) return []
        const needle = query.toLowerCase()
        return sample.filter(p => p.name.toLowerCase().indexOf(needle) >= 0).sort((a, b) => {
            const sa = saved[a.id] === "all", sb = saved[b.id] === "all"
            return sa === sb ? b.updated.localeCompare(a.updated) : sa ? -1 : 1
        })
    }
    function toggle(id) {
        const next = Object.assign({}, saved)
        if (next[id] === "all") delete next[id]
        else next[id] = "all"
        saved = next
        feedback = next[id] ? "Added immediately (preview)" : "Removed immediately (preview)"
    }
    onSceneChanged: {
        noPlaylists = scene === "menu-empty"
        query = scene === "menu-search" ? "deep" : ""
        saved = scene === "menu" ? {p2: "all", p3: "all"} : scene === "menu-partial" ? {p1: "all", p3: "partial", p5: "partial"} : {p2: "all", p3: "all"}
        feedback = "Illustrative menu · no playlist is touched"
        menuNew.search = query
    }

    // Stand-in for a track list with the "+" button.
    Column {
        x: 26; y: 26; width: 780; spacing: 8
        Text { text: "Night drive"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 28; font.bold: true }
        Repeater {
            model: 7
            delegate: Rectangle {
                required property int index
                width: parent.width; height: 48; radius: 6
                color: index === 2 ? Theme.selection : "transparent"
                Text { x: 16; anchors.verticalCenter: parent.verticalCenter; text: (index + 1) + "     Track " + (index + 1); color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14 }
                Icon { id: plus; anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; name: "add-playlist"; size: 20; color: index === 2 ? Theme.textPrimary : Theme.textMuted }
            }
        }
    }

    // The menu, drawn with either the current ("old") or the proposed ("new") metrics.
    component MenuBox: Rectangle {
        id: box
        property bool compact: true
        property alias search: field.text
        readonly property int menuWidth: compact ? 300 : 350
        readonly property int rowHeight: compact ? 44 : 68
        readonly property int coverSize: compact ? 32 : 48
        readonly property int pad: compact ? 12 : 16
        readonly property int nameSize: compact ? 13 : 18
        readonly property int subSize: compact ? 11 : 13
        readonly property int sectionHeight: compact ? 26 : 30
        readonly property int listCount: root.visibleChoices.length
        width: menuWidth
        height: compact ? Math.min(420, 12 * 2 + 18 + 30 + 40 + listCount * rowHeight + (listCount > 0 ? 26 + 8 : 0) + 24)
                        : Math.min(520, Math.max(245, listCount * 68 + 250))
        color: Theme.surface
        radius: 8
        border.color: Theme.separator

        Text { id: title; x: box.pad; y: box.pad; text: "Add to playlist"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: box.compact ? 13 : 16; font.weight: Font.DemiBold }
        TextField {
            id: field
            x: box.pad
            anchors.top: title.bottom; anchors.topMargin: box.compact ? 8 : 14
            width: parent.width - box.pad * 2
            height: box.compact ? 30 : 38
            leftPadding: box.compact ? 30 : 12
            placeholderText: "Search playlists"
            color: Theme.textPrimary; placeholderTextColor: Theme.textMuted
            font.family: Theme.fontFamily; font.pixelSize: box.compact ? 13 : 16
            onTextChanged: if (box.compact) root.query = text
            background: Rectangle { color: Theme.chrome; radius: 5; border.color: field.activeFocus ? Theme.focus : Theme.separator }
            Icon { visible: box.compact; x: 9; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 14; color: Theme.textMuted }
        }
        // "New playlist" row.
        Item {
            id: create
            x: box.pad - (box.compact ? 4 : 0)
            anchors.top: field.bottom; anchors.topMargin: box.compact ? 6 : 8
            width: parent.width - (box.pad - (box.compact ? 4 : 0)) * 2
            height: box.compact ? 40 : 36
            Rectangle { anchors.fill: parent; radius: 4; color: createMouse.containsMouse ? Theme.selection : "transparent" }
            Rectangle { visible: box.compact; x: 4; anchors.verticalCenter: parent.verticalCenter; width: 32; height: 32; radius: 4; color: Theme.selection
                Icon { anchors.centerIn: parent; name: "plus"; size: 16; color: Theme.textPrimary } }
            Text { x: box.compact ? 46 : 8; anchors.verticalCenter: parent.verticalCenter; text: box.compact ? "New playlist" : "+ New playlist"; color: box.compact ? Theme.textPrimary : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: box.compact ? 13 : 14 }
            MouseArea { id: createMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.feedback = "Would create a playlist with these tracks" }
        }
        ListView {
            id: list
            anchors.top: create.bottom; anchors.topMargin: 6
            anchors.bottom: parent.bottom; anchors.bottomMargin: box.compact ? box.pad : 52
            anchors.left: parent.left; anchors.right: parent.right
            clip: true
            model: root.visibleChoices
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}
            delegate: Item {
                id: entry
                required property var modelData
                required property int index
                readonly property string state: root.saved[modelData.id] || ""
                readonly property bool sectionStart: index === 0 || (root.saved[root.visibleChoices[index - 1].id] === "all") !== (state === "all")
                width: list.width
                height: box.rowHeight + (sectionStart ? box.sectionHeight : 0)
                Text {
                    visible: entry.sectionStart
                    x: box.pad
                    anchors.top: parent.top; anchors.topMargin: box.compact ? 8 : 0
                    text: entry.state === "all" ? "Saved in" : "Recently updated"
                    color: Theme.textSecondary; font.family: Theme.fontFamily
                    font.pixelSize: box.compact ? Theme.fontSizeCaption : 15
                    font.weight: Font.DemiBold
                    font.letterSpacing: box.compact ? 1.1 : 0
                    font.capitalization: box.compact ? Font.AllUppercase : Font.MixedCase
                }
                Rectangle {
                    x: box.pad - 4
                    y: entry.height - box.rowHeight
                    width: parent.width - (box.pad - 4) * 2
                    height: box.rowHeight
                    radius: 4
                    color: hit.containsMouse ? Theme.selection : "transparent"
                    CoverArt { x: 4; anchors.verticalCenter: parent.verticalCenter; width: box.coverSize; height: box.coverSize; radius: 3; pattern: entry.modelData.cover }
                    Column {
                        x: box.coverSize + 14; width: parent.width - box.coverSize - 14 - 40; anchors.verticalCenter: parent.verticalCenter; spacing: box.compact ? 1 : 4
                        Text { width: parent.width; text: entry.modelData.name; elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: box.nameSize }
                        Text { width: parent.width; text: entry.modelData.count + " tracks"; elide: Text.ElideRight; color: box.compact ? Theme.textMuted : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: box.subSize }
                    }
                    Icon { visible: entry.state !== "partial"; anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        name: entry.state === "all" ? "check" : "add-playlist"; size: box.compact ? 16 : 20; color: entry.state === "all" ? Theme.primary : Theme.textMuted }
                    Rectangle { visible: entry.state === "partial"; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 2; radius: 1; color: Theme.textSecondary }
                    MouseArea { id: hit; anchors.fill: parent; hoverEnabled: true; onClicked: root.toggle(entry.modelData.id) }
                }
            }
        }
        Text { visible: root.visibleChoices.length === 0 && !root.noPlaylists; anchors.horizontalCenter: parent.horizontalCenter; y: create.y + 60; text: "No playlist matches."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
        Text { visible: root.noPlaylists; anchors.horizontalCenter: parent.horizontalCenter; y: create.y + 60; text: "No playlists yet."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
        TextButton { visible: !box.compact; anchors.bottom: parent.bottom; anchors.right: parent.right; anchors.margins: 12; text: "Close"; kind: "ghost" }
        Text { visible: box.compact && root.scene !== "menu-compare"; anchors.bottom: parent.bottom; anchors.bottomMargin: -22; x: 0; text: "Esc or a click outside closes the menu"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
    }

    MenuBox { id: menuNew; compact: true; x: root.scene === "menu-compare" ? 540 : 870; y: root.scene === "menu-compare" ? 40 : 126 }
    MenuBox { id: menuOld; visible: root.scene === "menu-compare"; compact: false; x: 150; y: 40 }
    Text { visible: root.scene === "menu-compare"; x: 150; y: menuOld.y + menuOld.height + 10; text: "Current (350 × 520 max, 68 px rows)"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
    Text { visible: root.scene === "menu-compare"; x: 540; y: menuNew.y + menuNew.height + 10; text: "Proposed (300 × 420 max, 44 px rows)"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }

    Rectangle {
        height: 40
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        color: Theme.surface
        Text { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: root.feedback; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
    }
}
