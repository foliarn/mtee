import QtQuick
import QtQuick.Window
import Mtee

Window {
    id: root

    visible: true
    color: Theme.chrome
    title: "MTEE — UX/UI review mockups"
    width: 1440
    height: 900

    property string scene: "header-wide"
    readonly property bool isHeader: scene.startsWith("header-")
    readonly property bool isWave: scene.startsWith("wave-")
    readonly property bool hasInspector: scene === "header-wide" || scene === "header-medium"
    readonly property int railWidth: Theme.activityBarWidth
    readonly property int sidebarWidth: scene === "header-split" || scene === "columns-split" ? 220 : width < 1160 ? 0 : 220
    readonly property int inspectorWidth: hasInspector ? 300 : 0
    readonly property int contentLeft: railWidth + sidebarWidth
    readonly property int contentWidth: width - contentLeft - inspectorWidth

    Rectangle {
        id: titleBar
        x: 0
        y: 0
        width: root.width
        height: Theme.titleBarHeight
        color: Theme.chrome

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: "M"
            color: Theme.primary
            font.family: Theme.fontFamily
            font.pixelSize: 17
            font.bold: true
        }
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 48
            anchors.verticalCenter: parent.verticalCenter
            spacing: 18
            Repeater {
                model: ["File", "Edit", "View"]
                delegate: Text {
                    required property string modelData
                    text: modelData
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
        }
        Row {
            anchors.right: parent.right
            height: parent.height
            Repeater {
                model: ["−", "□", "×"]
                delegate: Rectangle {
                    required property string modelData
                    width: 46
                    height: titleBar.height
                    color: "transparent"
                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                    }
                }
            }
        }
    }

    Rectangle {
        id: activityRail
        x: 0
        y: titleBar.height
        width: root.railWidth
        height: root.height - titleBar.height
        color: Theme.chrome

        Column {
            anchors.top: parent.top
            anchors.topMargin: 12
            width: parent.width
            spacing: 8
            Repeater {
                model: ["E", "P", "C", "T", "·"]
                delegate: Item {
                    required property string modelData
                    required property int index
                    width: activityRail.width
                    height: 42
                    Rectangle {
                        width: 2
                        height: 26
                        color: index === 0 ? Theme.primary : "transparent"
                    }
                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData
                        color: index === 0 ? Theme.textPrimary : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 15
                        font.bold: true
                    }
                }
            }
        }
        Text {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 16
            anchors.horizontalCenter: parent.horizontalCenter
            text: "⚙"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 16
        }
    }

    Rectangle {
        id: sidebar
        x: root.railWidth
        y: titleBar.height
        width: root.sidebarWidth
        height: root.height - titleBar.height
        visible: width > 0
        color: Theme.sidebar

        Column {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 13
            Text {
                text: "EXPLORER"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.bold: true
                font.letterSpacing: 0.7
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Text { text: "⌄  Music Library"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { text: "   ›  Ambient"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { text: "   ⌄  Drum & Bass"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { text: "      ›  Liquid"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { text: "      ▸  Weekend crates"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Text { text: "   ›  House"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
        }
    }

    Rectangle {
        id: inspector
        x: root.width - root.inspectorWidth
        y: titleBar.height
        width: root.inspectorWidth
        height: root.height - titleBar.height
        visible: width > 0
        color: Theme.sidebar

        Column {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 14
            Row {
                spacing: 24
                Text { text: "Info"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
                Text { text: "Queue"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Text { text: "CURRENT SELECTION"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true }
            Rectangle { width: parent.width; height: 128; color: Theme.surface
                Text { anchors.centerIn: parent; text: "NO ARTWORK"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.letterSpacing: 1 }
            }
            Text { text: "Night Transit"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 16; font.bold: true }
            Text { text: "Mira Vale"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Text { text: "Duration         4:36\nFormat           FLAC\nBitrate          1,024 kb/s"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; lineHeight: 1.45 }
        }
    }

    Item {
        id: mainContent
        x: root.contentLeft
        y: titleBar.height
        width: root.contentWidth
        height: root.height - titleBar.height

        Loader {
            anchors.fill: parent
            sourceComponent: root.isHeader ? headerPage
                : root.scene.startsWith("columns-") ? columnsPage
                : wavePage
        }
    }

    component FolderHeader: Item {
        id: folderHeader
        property string folderName: "Weekend crates — long folder title"
        property string summary: "486 titles · 31 h 42 min · 8.6 GB"
        property bool searchFilled: false
        property bool split: false

        Rectangle { anchors.fill: parent; color: Theme.editor }
        Text {
            x: 24
            y: 21
            width: parent.width - 48
            text: folderHeader.folderName
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: folderHeader.width < 520 ? 19 : 27
            font.bold: true
            elide: Text.ElideRight
        }
        Text {
            x: 24
            y: 58
            width: parent.width - 48
            text: folderHeader.summary
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            elide: Text.ElideRight
        }

        Row {
            id: folderControls
            x: 12
            y: 88
            width: parent.width - 24
            height: 38
            spacing: 8

            Rectangle {
                id: searchField
                property int targetWidth: Math.max(96, Math.min(240, folderControls.width - 266))
                width: targetWidth
                height: 34
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.surface
                Rectangle { anchors.left: parent.left; width: 2; height: parent.height; color: folderHeader.searchFilled ? Theme.primary : "transparent" }
                Item {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    width: 14
                    height: 14
                    Rectangle { x: 0; y: 0; width: 9; height: 9; radius: 5; color: "transparent"; border.width: 1; border.color: Theme.textMuted }
                    Rectangle { x: 8; y: 9; width: 6; height: 1; rotation: 45; color: Theme.textMuted }
                }
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 34
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: folderHeader.searchFilled ? "night transit" : "Search this folder"
                    color: folderHeader.searchFilled ? Theme.textPrimary : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
                Text {
                    visible: folderHeader.searchFilled
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: "×"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: 16
                }
            }
            HeaderButton { label: "List"; width: folderControls.width < 520 ? 44 : 54; active: true }
            HeaderButton { label: "Artwork"; width: folderControls.width < 520 ? 64 : 76 }
            HeaderButton { label: "Choose columns"; width: folderControls.width < 520 ? 96 : 124 }
        }

        Rectangle { x: 0; y: 138; width: parent.width; height: 1; color: Theme.separator }
        Rectangle {
            x: 12
            y: 151
            width: parent.width - 24
            height: 30
            color: "transparent"
            Row {
                anchors.fill: parent
                spacing: 12
                Text { text: "TITLE"; width: parent.width * 0.38; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true }
                Text { text: "ARTIST"; width: parent.width * 0.25; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true }
                Text { text: "DATE CREATED"; width: parent.width * 0.23; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true; elide: Text.ElideRight }
            }
        }
        Column {
            x: 0
            y: 184
            width: parent.width
            Repeater {
                model: folderHeader.width < 520 ? 7 : 9
                delegate: TrackSampleRow {
                    required property int index
                    width: folderHeader.width
                    title: ["Night Transit", "Slow Current", "After Hours", "Glass Garden", "Parallel Lines", "Soft Focus", "Blue Circuit", "Underpass", "Last Light"][index]
                    artist: ["Mira Vale", "Orion Park", "Low Season", "Aster Bloom", "No Signal", "Satin Index", "June Relay", "Vera Moon", "New Pattern"][index]
                    selected: index === 1
                }
            }
        }
    }

    component HeaderButton: Rectangle {
        required property string label
        property bool active: false
        color: active ? Theme.selection : Theme.surface
        height: 32
        anchors.verticalCenter: parent.verticalCenter
        Rectangle { width: parent.width; height: 2; anchors.bottom: parent.bottom; color: parent.active ? Theme.primary : "transparent" }
        Text { anchors.centerIn: parent; text: parent.label; color: parent.active ? Theme.textPrimary : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight }
    }

    component TrackSampleRow: Rectangle {
        required property string title
        required property string artist
        property bool selected: false
        height: Theme.rowHeight
        color: selected ? Theme.selection : "transparent"
        Row {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 10
            Rectangle {
                width: 32
                height: 32
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.surface
            Text { anchors.centerIn: parent; text: "M"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
            }
            Column {
                width: Math.max(90, parent.width * 0.36)
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Text { width: parent.width; text: parent.parent.parent.title; color: parent.parent.parent.selected ? Theme.primary : Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12; elide: Text.ElideRight }
                Text { width: parent.width; text: parent.parent.parent.artist; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; elide: Text.ElideRight }
            }
            Text { width: Math.max(54, parent.width * 0.2); anchors.verticalCenter: parent.verticalCenter; text: "Mira Vale"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight }
            Text { width: Math.max(44, parent.width * 0.2); anchors.verticalCenter: parent.verticalCenter; text: "2024-06-18"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; elide: Text.ElideRight }
        }
    }

    component ColumnMenu: Rectangle {
        width: 260
        height: 470
        color: Theme.surface
        property string tableMode: "default"
        Column {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10
            Text { text: "COLUMNS"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.6 }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Repeater {
                model: [
                    ["Title", tableMode === "default" || tableMode === "many"],
                    ["Artist", tableMode !== "single"],
                    ["Album", tableMode === "many"],
                    ["Genre", tableMode === "many" || tableMode === "reduced"],
                    ["BPM", true], ["Key", tableMode !== "single"],
                    ["Duration", false], ["Format", tableMode === "many"],
                    ["Filename", false], ["Bitrate", tableMode === "many"],
                    ["Date created", tableMode !== "single"], ["Date modified", tableMode === "many"]
                ]
                delegate: Item {
                    required property var modelData
                    width: parent.width
                    height: 20
                    Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData[1] ? "☑" : "□"; color: parent.modelData[1] ? Theme.primary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
                    Text { anchors.left: parent.left; anchors.leftMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData[0]; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Row {
                spacing: 8
                Text { text: tableMode === "default" || tableMode === "many" ? "☑" : "□"; color: tableMode === "default" || tableMode === "many" ? Theme.primary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13 }
                Text { text: "Show artwork"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Text { text: "Reset columns"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
        }
    }

    component DataTable: Item {
        id: table
        property string mode: "default"
        property bool menuOpen: false
        readonly property var columnFields: mode === "default" ? [
            ["TITLE", 2.0, "title"], ["ARTIST", 1.2, "plain"], ["DATE CREATED", 1.25, "plain"], ["BPM", 0.52, "plain"], ["KEY", 0.5, "key"]
        ] : mode === "many" ? [
            ["TITLE", 1.55, "title"], ["ARTIST", 1.0, "plain"], ["ALBUM", 1.0, "plain"], ["GENRE", 0.8, "plain"], ["DATE CREATED", 1.15, "plain"], ["DATE MODIFIED", 1.15, "plain"], ["FORMAT", 0.62, "plain"], ["BITRATE", 0.62, "plain"], ["SIZE", 0.62, "plain"]
        ] : mode === "reduced" ? [
            ["ARTIST", 1.5, "plain"], ["GENRE", 0.95, "plain"], ["DATE CREATED", 1.15, "plain"], ["BPM", 0.52, "plain"], ["KEY", 0.5, "key"]
        ] : [["BPM", 0.8, "plain"]]

        function totalWeight() {
            let sum = 0
            for (let i = 0; i < columnFields.length; ++i)
                sum += columnFields[i][1]
            return sum
        }
        function cellValue(fieldIndex, rowIndex) {
            const field = columnFields[fieldIndex]
            if (field[2] === "title")
                return rowIndex === 2 ? "Night Transit" : ["Slow Current", "After Hours", "Glass Garden", "Parallel Lines", "Soft Focus", "Blue Circuit", "Underpass", "Last Light", "Morning Air", "Spring Static"][rowIndex]
            if (field[2] === "key")
                return "8A"
            return field[0] === "ARTIST" ? ["Orion Park", "Low Season", "Mira Vale", "Aster Bloom", "No Signal", "Satin Index", "June Relay", "Vera Moon", "New Pattern", "Mira Vale"][rowIndex] : field[0] === "DATE CREATED" ? "2026-08-12"
                : field[0] === "DATE MODIFIED" ? "2026-09-03"
                : field[0] === "ALBUM" ? "Blue Signals"
                : field[0] === "GENRE" ? "Liquid"
                : field[0] === "FORMAT" ? "FLAC"
                : field[0] === "BITRATE" ? "1,024"
                : field[0] === "SIZE" ? "41 MB" : "174"
        }

        Rectangle { anchors.fill: parent; color: Theme.editor }
        Text { x: 24; y: 19; width: parent.width - 48; text: table.mode === "many" ? "New additions · extended details" : "UK Garage · recently added"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 24; font.bold: true; elide: Text.ElideRight }
        Text { x: 24; y: 54; text: "128 titles · 9 h 12 min · 2.1 GB"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }

        Row {
            id: listControls
            x: 16
            y: 82
            spacing: 8
            Rectangle { width: Math.min(220, Math.max(120, table.width - 560)); height: 32; color: Theme.surface
                Text { anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: "Search this folder"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
            }
            HeaderButton { label: "List"; width: 50; active: true }
            HeaderButton { label: "Artwork"; width: 68 }
            Rectangle { width: 118; height: 32; color: Theme.selection; anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: "Choose columns"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 10 }
            }
        }

        Rectangle {
            id: tableHeader
            x: 16
            y: 132
            width: parent.width - 32
            height: 30
            color: "transparent"
            Row {
                anchors.fill: parent
                spacing: 10
                Text { text: ""; width: table.mode === "reduced" || table.mode === "single" ? 44 : 36; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                Text { visible: table.mode === "default"; text: ""; width: 40; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                Repeater {
                    model: table.columnFields.length
                    delegate: Text {
                        required property int index
                        width: Math.max(46, (table.width - 150) * table.columnFields[index][1] / table.totalWeight())
                        text: table.columnFields[index][0]
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: 9
                        font.bold: true
                        elide: Text.ElideRight
                    }
                }
                Text { text: ""; width: 50; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
            }
        }
        Rectangle { x: 16; y: 162; width: parent.width - 32; height: 1; color: Theme.separator }
        Column {
            id: dataRows
            x: 16
            y: 163
            width: parent.width - 32
            Repeater {
                model: 10
                delegate: Item {
                    id: rowItem
                    required property int index
                    width: dataRows.width
                    height: Theme.rowHeight
                    Rectangle { anchors.fill: parent; color: index === 2 ? Theme.selection : "transparent" }
                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 10
                        Column {
                            width: table.mode === "reduced" || table.mode === "single" ? 44 : 36
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: index === 2 ? ">" : "·"; color: index === 2 ? Theme.primary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: index === 2 }
                            Text { text: "i"; color: index === 2 ? Theme.textPrimary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.italic: true }
                        }
                        Rectangle {
                            visible: table.mode === "default" || table.mode === "many"
                            width: visible ? 34 : 0
                            height: 34
                            anchors.verticalCenter: parent.verticalCenter
                            color: Theme.surface
                            Text { anchors.centerIn: parent; text: "M"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
                        }
                        Repeater {
                            model: table.columnFields.length
                            delegate: Text {
                                required property int index
                                property int rowIndex: rowItem.index
                                property var field: table.columnFields[index]
                                width: Math.max(46, (table.width - 150) * field[1] / table.totalWeight())
                                anchors.verticalCenter: parent.verticalCenter
                                text: table.cellValue(index, rowIndex)
                                color: field[2] === "title" ? (rowIndex === 2 ? Theme.primary : Theme.textPrimary) : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: 11
                                font.bold: field[2] === "title"
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            visible: table.menuOpen
            x: parent.width - width - 22
            y: 116
            width: 260
            height: 470
            color: "transparent"
            ColumnMenu { anchors.fill: parent; tableMode: table.mode }
        }
    }

    component WaveLane: Item {
        id: lane
        property string variant: "mono"
        property real cursor: 0.283
        property bool playing: true
        property int barCount: Math.max(36, Math.floor(width / 5))
        property int step: Math.max(3, Math.floor(width / barCount))
        property int barWidth: Math.max(1, Math.min(3, step - 2))
        property string timeText: "1:18"

        function envelope(index) {
            const x = index / barCount
            const intro = x < 0.16 ? 0.14 + x * 1.7 : 0.42
            const build = x > 0.32 && x < 0.47 ? 0.76 : 0
            const breakDown = x > 0.62 && x < 0.72 ? 0.19 : 0
            const outro = x > 0.9 ? 0.2 + (1 - x) * 0.5 : 0
            const rhythm = Math.abs(Math.sin(index * 1.31) * 0.47 + Math.cos(index * 0.39) * 0.31)
            return Math.max(0.035, Math.min(0.95, Math.max(intro, build, breakDown, outro) * (0.28 + rhythm)))
        }
        function bandLevel(index, band) {
            const offset = band * 19
            const shape = Math.abs(Math.sin(index * (0.21 + band * 0.037) + offset) * 0.54 + Math.cos(index * (0.083 + band * 0.02)) * 0.37)
            return Math.max(0.08, Math.min(0.95, envelope(index) * (0.3 + shape)))
        }
        function bandColor(band) {
            return band === 0 ? Theme.secondary : band === 1 ? Theme.primary : "#54D6FF"
        }
        function mixedColor(index) {
            const low = bandLevel(index, 0)
            const mid = bandLevel(index, 1)
            const high = bandLevel(index, 2)
            return Qt.rgba(Math.min(1, low * 0.95 + mid * 0.08), Math.min(1, mid * 0.95 + high * 0.08), Math.min(1, high * 0.95 + low * 0.08), 1)
        }

        Rectangle { anchors.fill: parent; color: Theme.editor }
        Repeater {
            model: lane.barCount
            delegate: Item {
                required property int index
                x: index * lane.step
                width: lane.barWidth
                height: lane.height
                property real alpha: (index + 0.5) / lane.barCount <= lane.cursor ? 0.35 : 1

                Rectangle {
                    visible: lane.variant !== "bands"
                    width: parent.width
                    height: Math.max(1, lane.envelope(parent.index) * lane.height * 0.88)
                    y: (lane.height - height) / 2
                    color: lane.variant === "rgb" ? lane.mixedColor(parent.index) : Theme.textSecondary
                    opacity: parent.alpha
                }
                Rectangle {
                    visible: lane.variant === "bands"
                    property real bandHeight: parent.height / 3
                    width: parent.width
                    height: Math.max(1, lane.bandLevel(parent.index, 0) * bandHeight * 0.86)
                    y: (bandHeight - height) / 2
                    color: lane.bandColor(0)
                    opacity: parent.alpha
                }
                Rectangle {
                    visible: lane.variant === "bands"
                    property real bandHeight: parent.height / 3
                    width: parent.width
                    height: Math.max(1, lane.bandLevel(parent.index, 1) * bandHeight * 0.86)
                    y: bandHeight + (bandHeight - height) / 2
                    color: lane.bandColor(1)
                    opacity: parent.alpha
                }
                Rectangle {
                    visible: lane.variant === "bands"
                    property real bandHeight: parent.height / 3
                    width: parent.width
                    height: Math.max(1, lane.bandLevel(parent.index, 2) * bandHeight * 0.86)
                    y: bandHeight * 2 + (bandHeight - height) / 2
                    color: lane.bandColor(2)
                    opacity: parent.alpha
                }
            }
        }
        Rectangle {
            x: Math.max(0, Math.min(lane.width - width, lane.cursor * lane.width))
            y: 0
            width: 1
            height: lane.height
            color: Theme.textPrimary
            z: 2
        }
        Rectangle {
            x: Math.max(0, Math.min(lane.width - width, lane.cursor * lane.width - width / 2))
            y: -20
            width: 52
            height: 17
            color: Theme.textPrimary
            z: 3
            Text { anchors.centerIn: parent; text: lane.timeText; color: Theme.textOnColor; font.family: Theme.fontFamily; font.pixelSize: 9; font.bold: true }
        }
    }

    component WaveReview: Item {
        id: waveReview
        property bool edgeStates: false
        property bool narrow: false
        property bool positionMatrix: false
        Rectangle { anchors.fill: parent; color: Theme.editor }
        Column {
            anchors.fill: parent
            anchors.margins: 32
            spacing: 18
            Row {
                width: parent.width
                spacing: 18
                Column {
                    width: parent.width - 250
                    spacing: 7
                    Text { text: "FULLSCREEN PLAYER · PLAYING FROM DNB ARCHIVE"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.6 }
                    Text { width: parent.width; text: "Night Transit"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 25; font.bold: true; elide: Text.ElideRight }
                    Text { text: "Mira Vale · Synthetic comparison source"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                }
                Rectangle {
                    width: 220
                    height: 66
                    color: Theme.surface
                    Text { anchors.centerIn: parent; text: "SYNTHETIC DATA\nCOLOR STUDY ONLY"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true; horizontalAlignment: Text.AlignHCenter; lineHeight: 1.35 }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }

            Column {
                width: parent.width
                spacing: 20
                Repeater {
                    model: [
                        ["MONOCHROME", "mono", "Existing amplitude extrema; no new signal data."],
                        ["3 BANDS", "bands", "Synthetic low / mid / high energy lanes."],
                        ["RGB MIX", "rgb", "Synthetic additive low / mid / high colour blend."]
                    ]
                    delegate: Item {
                        id: variantRow
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: waveReview.positionMatrix ? 150 : 122
                        Text { x: 0; y: 0; text: parent.modelData[0]; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.5 }
                        Text { x: 0; y: 17; width: 180; text: parent.modelData[2]; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9; wrapMode: Text.WordWrap; lineHeight: 1.2 }
                        WaveLane {
                            x: 192
                            y: 24
                            width: parent.width - 208
                            height: waveReview.edgeStates ? 64 : 64
                            visible: !waveReview.positionMatrix
                            variant: parent.modelData[1]
                            cursor: waveReview.edgeStates ? [0, 0.5, 1][index] : 0.283
                            playing: !waveReview.edgeStates || index === 1
                            timeText: waveReview.edgeStates ? ["0:00", "2:18", "4:36"][index] : "1:18"
                        }
                        Row {
                            visible: waveReview.positionMatrix
                            x: 192
                            y: 24
                            width: parent.width - 208
                            spacing: 12
                            Repeater {
                                model: [
                                    [0, "0:00", "PLAYING"],
                                    [0.283, "1:18", "PLAYING"],
                                    [1, "4:36", "PAUSED"]
                                ]
                                delegate: Item {
                                    required property var modelData
                                    width: (parent.width - 24) / 3
                                    height: 100
                                    Text { text: parent.modelData[1] + " · " + parent.modelData[2]; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 8 }
                                    WaveLane {
                                        y: 20
                                        width: parent.width
                                        height: 56
                                        variant: variantRow.modelData[1]
                                        cursor: parent.modelData[0]
                                        timeText: parent.modelData[1]
                                    }
                                    Text { y: 82; text: "0:00                                      4:36"; width: parent.width; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 7 }
                                }
                            }
                        }
                        Text {
                            x: 192
                            y: 94
                            visible: !waveReview.positionMatrix
                            text: waveReview.edgeStates ? ["PLAYING · HEAD AT START", "PAUSED · POSITION RETAINED", "PLAYING · HEAD AT END"][index] : "PLAYING · 1:18 / 4:36"
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: 9
                        }
                    }
                }
            }

            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Row {
                spacing: 18
                Text { text: "0:00"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
                Text { text: "Shuffle     Previous     Pause     Next     Repeat"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10 }
                Text { text: "4:36"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
            }
            Row {
                visible: waveReview.edgeStates || waveReview.narrow
                width: parent.width
                spacing: 12
                Rectangle {
                    width: (parent.width - parent.spacing) / 2
                    height: 50
                    color: Theme.surface
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text { text: "PREPARING"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 9; font.bold: true }
                        Text { text: "Generating waveform…"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9 }
                    }
                }
                Rectangle {
                    width: (parent.width - parent.spacing) / 2
                    height: 50
                    color: Theme.surface
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 3
                        Text { text: "UNAVAILABLE"; color: Theme.danger; font.family: Theme.fontFamily; font.pixelSize: 9; font.bold: true }
                        Text { text: "Audio source could not be read"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9; elide: Text.ElideRight; width: parent.parent.width - 24 }
                    }
                }
            }
            Text {
                visible: waveReview.narrow
                width: parent.width
                text: "NARROW · " + Math.round(waveReview.width - 64) + " px · marker clamped to the visible waveform"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: 9
            }
        }
    }

    Component {
        id: headerPage
        Item {
            Rectangle { anchors.fill: parent; color: Theme.editor }
            FolderHeader {
                anchors.fill: parent
                visible: root.scene !== "header-split"
                folderName: "Weekend crates — long folder title to check available space"
                summary: "486 titles · 31 h 42 min · 8.6 GB"
                searchFilled: root.scene === "header-medium"
            }
            Row {
                anchors.fill: parent
                visible: root.scene === "header-split"
                spacing: 1
                FolderHeader {
                    width: (parent.width - 1) / 2
                    height: parent.height
                    folderName: "Drum & Bass — Weekend crates"
                    summary: "84 titles · 5 h 13 min · 1.4 GB"
                    searchFilled: false
                    split: true
                }
                Rectangle { width: 1; height: parent.height; color: Theme.separator }
                FolderHeader {
                    width: (parent.width - 1) / 2
                    height: parent.height
                    folderName: "UK Garage"
                    summary: "62 titles · 4 h 06 min · 1.1 GB"
                    searchFilled: true
                    split: true
                }
            }
        }
    }
    Component {
        id: columnsPage
        Item {
            anchors.fill: parent
            Rectangle { anchors.fill: parent; color: Theme.editor }
            Row {
                anchors.fill: parent
                visible: root.scene === "columns-split"
                spacing: 1
                DataTable {
                    width: (parent.width - 1) / 2
                    height: parent.height
                    mode: "single"
                    menuOpen: true
                }
                Rectangle { width: 1; height: parent.height; color: Theme.separator }
                DataTable {
                    width: (parent.width - 1) / 2
                    height: parent.height
                    mode: "reduced"
                    menuOpen: false
                }
            }
            DataTable {
                anchors.fill: parent
                visible: root.scene !== "columns-split"
                mode: root.scene === "columns-menu" ? "default"
                    : root.scene === "columns-many" ? "many"
                    : root.scene === "columns-reduced" ? "reduced" : "single"
                menuOpen: root.scene === "columns-menu" || root.scene === "columns-single"
            }
        }
    }
    Component {
        id: wavePage
        WaveReview {
            anchors.fill: parent
            edgeStates: root.scene === "wave-edges"
            narrow: root.scene === "wave-narrow"
            positionMatrix: root.scene === "wave-positions"
        }
    }
}
