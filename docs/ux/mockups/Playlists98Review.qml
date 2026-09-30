import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../../../src/mtee/qml/components"

// Plan 98 review only. Every state and action is local to this window.
ApplicationWindow {
    id: root
    visible: true
    width: 1440
    height: 900
    minimumWidth: 880
    minimumHeight: 600
    title: "MTEE — playlist interactions review"
    color: Theme.editor
    property string scene: "playback-states"
    property bool coverHovered: scene === "cover-hover"
    property bool editing: scene === "title-edit"
    property bool playing: scene !== "playback-paused"
    property int activeRow: 1
    readonly property bool dragging: scene.indexOf("drag-") === 0 || scene.indexOf("drop-") === 0 || scene.indexOf("insert-") === 0
    readonly property bool multiple: scene === "drag-multiple" || scene === "drop-playlist" || scene === "insert-artwork"
    readonly property bool artwork: scene === "insert-artwork"
    readonly property bool compact: width < 1160
    readonly property var tracks: [
        { title: "Afterlight", artist: "Northline", album: "Transit", duration: "5:04", pattern: 0 },
        { title: "Control (Original Mix)", artist: "Second Signal", album: "Night drive", duration: "4:18", pattern: 3 },
        { title: "Low Orbit", artist: "Velar", album: "Low Orbit", duration: "4:56", pattern: 6 },
        { title: "Wired", artist: "Second Signal", album: "Night drive", duration: "4:12", pattern: 2 },
        { title: "A Very Long Track Title That Must Stay Readable in a Narrow Panel", artist: "The Night Array", album: "Signals", duration: "6:34", pattern: 5 }
    ]
    function caption() {
        if (scene === "creation-menu" || scene === "creation-resume") return "Create in one click · no name dialog"
        if (scene === "creation-opened") return "Created and opened · Untitled playlist 12"
        if (scene === "title-edit") return "Click the title to edit name and description"
        if (scene === "cover-hover") return "Hover the cover to reveal Change cover"
        if (scene === "drop-playlist") return "Drop on a compatible playlist"
        if (scene === "insert-list") return "Insert before this track · Custom order"
        if (scene === "insert-artwork") return "Insert between cards · Custom order"
        if (scene === "drag-multiple") return "Three selected tracks follow the pointer"
        if (scene === "drag-single") return "Title and artist follow the pointer"
        return "Play/Pause states · one fixed slot before cover art"
    }
    onSceneChanged: {
        coverHovered = scene === "cover-hover"
        editing = scene === "title-edit"
        playing = scene !== "playback-paused"
    }

    Rectangle { anchors.fill: parent; color: Theme.editor }
    Rectangle {
        id: rail
        width: 52; anchors.top: parent.top; anchors.bottom: parent.bottom
        color: Theme.chrome
        Column {
            anchors.top: parent.top; anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter; spacing: 26
            Text { text: "M"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 24; font.bold: true }
            Icon { name: "search"; color: Theme.textSecondary; size: 22 }
            Icon { name: "music"; color: Theme.textSecondary; size: 22 }
        }
    }
    Rectangle {
        id: sidebar
        x: rail.width; width: root.compact ? 204 : 246
        anchors.top: parent.top; anchors.bottom: parent.bottom
        color: Theme.sidebar
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.separator }
        Text { x: 18; y: 22; text: "Library"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 18; font.bold: true }
        Text { x: 18; y: 77; text: "PLAYLISTS"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
        Rectangle {
            id: plus
            x: parent.width - 47; y: 69; width: 30; height: 30
            color: scene === "creation-menu" || scene === "creation-resume" ? Theme.selection : "transparent"
            Text { anchors.centerIn: parent; text: "+"; color: Theme.textPrimary; font.pixelSize: 22 }
            MouseArea { anchors.fill: parent; onClicked: root.scene = "creation-menu" }
        }
        Column {
            x: 10; y: 113; width: parent.width - 20; spacing: 3
            Repeater {
                model: ["♥  Liked tracks", "▸  Sets", "▸  Warm-up", "♫  Night drive", "♫  Untitled playlist 12", "♫  Deep focus"]
                Rectangle {
                    required property int index
                    required property string modelData
                    width: parent.width; height: 36
                    color: index === 4 && scene === "creation-opened" ? Theme.selection : "transparent"
                    border.width: index === 3 && scene === "drop-playlist" ? 2 : 0
                    border.color: Theme.primary
                    Text { x: 11; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 22; text: modelData; elide: Text.ElideRight; color: index === 4 && scene === "creation-opened" ? Theme.primary : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                }
            }
        }
        Rectangle {
            x: 13; y: 84; width: Math.min(224, sidebar.width - 20); height: scene === "creation-resume" ? 145 : 112
            z: 5; visible: scene === "creation-menu" || scene === "creation-resume"; color: Theme.surface
            border.width: 1; border.color: Theme.separator
            Column {
                anchors.fill: parent; anchors.margins: 5
                Repeater {
                    model: scene === "creation-resume" ? ["New playlist", "New folder", "Resume interrupted import…", "Import playlist"] : ["New playlist", "New folder", "Import playlist"]
                    Rectangle {
                        required property string modelData
                        width: parent.width; height: 33; color: "transparent"
                        Text { x: 11; anchors.verticalCenter: parent.verticalCenter; text: modelData; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                        MouseArea { anchors.fill: parent; onClicked: root.scene = "creation-opened" }
                    }
                }
            }
        }
    }
    Item {
        id: content
        x: sidebar.x + sidebar.width; width: parent.width - x - (root.scene === "playback-states" && !root.compact ? 264 : 0)
        anchors.top: parent.top; anchors.bottom: player.top
        clip: true
        Rectangle { anchors.fill: parent; color: Theme.editor }
        Rectangle {
            id: tabbar
            width: parent.width; height: 45; color: Theme.chrome
            Text { x: 22; anchors.verticalCenter: parent.verticalCenter; text: "Night drive"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { x: 178; anchors.verticalCenter: parent.verticalCenter; text: "×"; color: Theme.textMuted; font.pixelSize: 18 }
            Rectangle { x: 12; anchors.bottom: parent.bottom; width: 176; height: 2; color: Theme.primary }
        }
        Item {
            id: heading
            x: root.compact ? 22 : 34; y: 76
            width: parent.width - x - 24; height: root.compact ? 172 : 198
            PlaylistCover { id: largeCover; x: 0; y: 0; width: root.compact ? 152 : 190; height: width; covers: [] }
            Grid {
                anchors.fill: largeCover; columns: 2
                Repeater { model: 4; CoverArt { required property int index; width: largeCover.width / 2; height: largeCover.height / 2; pattern: index * 2 } }
            }
            Rectangle {
                anchors.fill: largeCover; color: "#73000000"; visible: root.coverHovered
                Text { anchors.centerIn: parent; text: "Change cover"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14; font.bold: true }
            }
            MouseArea { anchors.fill: largeCover; hoverEnabled: true; onEntered: root.coverHovered = true; onExited: root.coverHovered = false; onClicked: root.coverHovered = true }
            Column {
                x: largeCover.width + 28; y: 5; width: parent.width - x; spacing: 11
                Text { text: "PLAYLIST"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
                Text {
                    id: titleText; width: parent.width; text: scene === "creation-opened" ? "Untitled playlist 12" : "Night drive"
                    elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily
                    font.pixelSize: root.compact ? 30 : 40; font.bold: true
                    MouseArea { anchors.fill: parent; onClicked: root.editing = true }
                }
                Text { width: parent.width; text: "Late journeys and bright horizons."; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 14 }
                Text { text: "5 titles  ·  24 min  ·  You"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Row {
                    spacing: 10
                    Rectangle { width: 72; height: 34; color: Theme.primary; Text { anchors.centerIn: parent; text: "Play"; color: Theme.textOnColor; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true } }
                    Rectangle { width: 80; height: 34; color: Theme.surface; Text { anchors.centerIn: parent; text: "Shuffle"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 } }
                }
            }
        }
        Text {
            x: heading.x; y: heading.y + heading.height + 14
            text: root.caption(); color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 12
        }
        Rectangle {
            id: listArea
            x: heading.x; y: heading.y + heading.height + 45
            width: parent.width - x - 24; height: parent.height - y - 22
            color: "transparent"
            Text { x: 0; y: 0; text: root.artwork ? "ARTWORK" : "CUSTOM ORDER"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
            Item {
                id: listRows
                anchors.top: parent.top; anchors.topMargin: 25
                width: parent.width; height: parent.height - 25
                visible: !root.artwork
                Repeater {
                    model: root.tracks
                    Rectangle {
                        required property int index
                        required property var modelData
                        x: 0; y: index * 59; width: listRows.width; height: 56
                        color: index === 1 || (root.dragging && index === 2) ? Theme.surface : "transparent"
                        Rectangle { x: 0; y: -2; width: parent.width; height: 3; color: Theme.primary; visible: root.scene === "insert-list" && index === 2 }
                        Rectangle {
                            id: playSlot; x: 8; width: 32; height: parent.height; color: "transparent"
                            Icon {
                                anchors.centerIn: parent
                                name: index === root.activeRow ? (root.playing ? "pause" : "play") : "play"
                                visible: index === root.activeRow || (root.scene === "playback-states" && index === 2)
                                color: Theme.textPrimary; size: 16
                            }
                            MouseArea { anchors.fill: parent; onClicked: { root.activeRow = index; root.playing = !root.playing } }
                        }
                        CoverArt { x: 52; anchors.verticalCenter: parent.verticalCenter; width: 40; height: 40; pattern: modelData.pattern }
                        Column {
                            x: 105; anchors.verticalCenter: parent.verticalCenter; width: parent.width - x - 140; spacing: 3
                            Text { width: parent.width; text: modelData.title; elide: Text.ElideRight; color: index === root.activeRow ? Theme.primary : Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                            Text { width: parent.width; text: modelData.artist; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                        }
                        Text { anchors.right: parent.right; anchors.rightMargin: 20; anchors.verticalCenter: parent.verticalCenter; text: modelData.duration; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    }
                }
                Rectangle { x: 0; y: 5 * 59; width: parent.width; height: 3; color: Theme.primary; visible: root.scene === "insert-list" }
            }
            Flow {
                x: 0; y: 25; width: parent.width; spacing: 12; visible: root.artwork
                Repeater {
                    model: root.tracks
                    Rectangle {
                        required property int index
                        required property var modelData
                        width: root.compact ? 126 : 152; height: width + 54; color: Theme.surface
                        CoverArt { x: 8; y: 8; width: parent.width - 16; height: width; pattern: modelData.pattern }
                        Text { x: 8; y: parent.width - 2; width: parent.width - 16; text: modelData.title; elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                        Text { x: 8; y: parent.width + 17; width: parent.width - 16; text: modelData.artist; elide: Text.ElideRight; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                        Rectangle { x: -7; y: 0; width: 3; height: parent.height; color: Theme.primary; visible: index === 2 }
                    }
                }
            }
        }
    }
    Rectangle {
        x: content.x + content.width; width: parent.width - x
        anchors.top: parent.top; anchors.bottom: player.top
        visible: width > 0; color: Theme.sidebar
        Rectangle { width: 1; height: parent.height; color: Theme.separator }
        Text { x: 20; y: 26; text: "Info"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 19; font.bold: true }
        Text { x: 20; y: 75; text: "Control (Original Mix)"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
        Text { x: 20; y: 99; text: "Second Signal"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }
    Rectangle {
        id: player; x: sidebar.x + sidebar.width; width: parent.width - x; anchors.bottom: parent.bottom
        height: 72; color: Theme.chrome
        Rectangle { width: parent.width; height: 1; color: Theme.separator }
        Row { x: 24; anchors.verticalCenter: parent.verticalCenter; spacing: 26
            Icon { name: "previous"; color: Theme.textPrimary; size: 18 }
            Icon { name: root.playing ? "pause" : "play"; color: Theme.textPrimary; size: 20 }
            Icon { name: "next"; color: Theme.textPrimary; size: 18 }
        }
        Text { x: 180; anchors.verticalCenter: parent.verticalCenter; text: "Control (Original Mix)  ·  Second Signal"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }
    Rectangle {
        x: content.x + Math.min(290, content.width * 0.30); y: content.y + 405
        width: Math.min(330, content.width * 0.45); height: root.multiple ? 76 : 58
        z: 10; visible: root.dragging; color: Theme.surface
        border.width: 1; border.color: Theme.separator
        Text { x: 13; y: 11; width: parent.width - 26; text: root.multiple ? "Afterlight — Northline" : "Low Orbit — Velar"; elide: Text.ElideRight; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
        Text { x: 13; y: 35; visible: root.multiple; text: "and 2 other tracks…"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }
    Rectangle {
        anchors.centerIn: parent; width: Math.min(460, parent.width - 60); height: 230
        z: 20; visible: root.editing; color: Theme.surface
        border.width: 1; border.color: Theme.separator
        Column {
            anchors.fill: parent; anchors.margins: 22; spacing: 11
            Text { text: "Edit playlist"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 21; font.bold: true }
            Text { text: "Name"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            TextField { width: parent.width; text: "Night drive"; color: Theme.textPrimary; font.family: Theme.fontFamily; background: Rectangle { color: Theme.editor; border.color: Theme.separator; border.width: 1 } }
            Text { text: "Description"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            TextField { width: parent.width; text: "Late journeys and bright horizons."; color: Theme.textPrimary; font.family: Theme.fontFamily; background: Rectangle { color: Theme.editor; border.color: Theme.separator; border.width: 1 } }
            Row {
                spacing: 12
                Text { text: "Cancel"; color: Theme.textSecondary; font.family: Theme.fontFamily; MouseArea { anchors.fill: parent; onClicked: root.editing = false } }
                Text { text: "Save"; color: Theme.primary; font.family: Theme.fontFamily; MouseArea { anchors.fill: parent; onClicked: root.editing = false } }
            }
        }
    }
}
