import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Review only. Every action changes illustrative, in-memory data.
ApplicationWindow {
    id: root
    objectName: "playlistReviewWindow"
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    width: 1440
    height: 900
    minimumWidth: 620
    minimumHeight: 640
    title: "MTEE — playlist review (illustrative data)"
    color: Theme.editor
    property string scene: "playlist"
    property string playlistName: "Night drive"
    property string description: "Heavy bass, late turns. A crate for the road home."
    property bool emptyPlaylist: false
    property bool searchOpen: false
    property bool shuffle: false
    property bool playing: false
    property bool artwork: false
    property bool pinned: true
    property string playingId: ""
    property string query: ""
    property string sortMode: "Custom order"
    property string exportKind: "zip"
    property string feedback: "Illustrative data · no files or database are changed"
    property var likes: ({ a: true, c: true })
    property var membership: ({ night: true, bass: true })
    property bool folderOpen: true
    property bool nestedOpen: true
    readonly property int sidebarWidth: width < 940 ? 0 : 240
    readonly property var tracks: [
        { id: "a", title: "Control (Original Mix)", artist: "Northline", album: "Control", bpm: "140.0", key: "8A", length: "3:48", cover: 0 },
        { id: "b", title: "Wired", artist: "Second Signal", album: "Night Shift", bpm: "142.0", key: "9A", length: "4:12", cover: 1 },
        { id: "c", title: "Low Orbit", artist: "Velar", album: "Low Orbit", bpm: "140.0", key: "8A", length: "4:56", cover: 3 },
        { id: "d", title: "Afterlight (Extended Mix)", artist: "Northline", album: "Afterlight", bpm: "—", key: "—", length: "5:04", cover: -1, missing: true },
        { id: "e", title: "Descent", artist: "Velar", album: "Descent", bpm: "145.0", key: "7A", length: "3:36", cover: 4 },
        { id: "f", title: "Last Exit", artist: "Second Signal", album: "Night Shift", bpm: "142.0", key: "9A", length: "4:38", cover: 5 }
    ]
    readonly property var destinations: [
        { id: "night", name: "Night drive", info: "6 tracks", cover: 0 },
        { id: "bass", name: "Bass essentials", info: "Bass crates · 28 tracks", cover: 1 },
        { id: "warm", name: "Warm-up", info: "Sets / Opening · 12 tracks", cover: 3 },
        { id: "late", name: "Late set", info: "Sets · 19 tracks", cover: 5 }
    ]
    readonly property var visibleTracks: {
        if (emptyPlaylist) return []
        let result = tracks.filter(t => (scene !== "liked" || likes[t.id])
            && (t.title + " " + t.artist + " " + t.album).toLowerCase().indexOf(query.toLowerCase()) >= 0)
        if (sortMode === "Title A–Z") result.sort((a, b) => a.title.localeCompare(b.title))
        return result
    }
    readonly property int playableCount: visibleTracks.filter(t => !t.missing).length

    function toggleLike(identity) {
        let next = Object.assign({}, likes)
        next[identity] = !next[identity]
        likes = next
    }
    function toggleMember(identity) {
        let next = Object.assign({}, membership)
        next[identity] = !next[identity]
        membership = next
        feedback = next[identity] ? "Added to playlist" : "Removed from playlist"
    }
    function configureScene() {
        addMenu.close(); createMenu.close(); detailsMenu.close(); columnMenu.close(); transfer.close(); locate.close()
        emptyPlaylist = scene === "empty"
        playlistName = emptyPlaylist ? "New playlist" : scene === "liked" ? "Liked tracks" : "Night drive"
        query = scene === "search" ? "Northline" : ""
        searchOpen = scene === "search"
        artwork = scene === "artwork"
        playing = false
        playingId = ""
        sortMode = "Custom order"
        if (scene === "menu") addMenu.open()
        if (scene === "columns") columnMenu.open()
        if (scene === "create") createMenu.open()
        if (scene === "export") { transfer.mode = "export"; transfer.open() }
        if (scene === "import") { transfer.mode = "import"; transfer.open() }
        if (scene === "locate") locate.open()
    }
    onSceneChanged: configureScene()

    component Label: Text {
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 14
        elide: Text.ElideRight
    }
    component ReviewIcon: Item {
        property string name: ""
        property color ink: Theme.textSecondary
        property int size: 18
        width: size; height: size
        Icon {
            anchors.fill: parent
            name: parent.name
            size: parent.size
            color: parent.ink
            visible: parent.name !== "heart" && parent.name !== "heart-filled" && parent.name !== "pin"
        }
        Image {
            anchors.fill: parent
            visible: parent.name === "heart" || parent.name === "heart-filled" || parent.name === "pin"
            source: visible ? "icons/" + parent.name + ".svg" : ""
            sourceSize: Qt.size(48, 48)
        }
    }
    component Action: AbstractButton {
        id: action
        property string glyph: ""
        property bool active: false
        property bool primary: false
        property bool circular: false
        property color ink: primary ? Theme.textOnColor : active ? Theme.primary : Theme.textSecondary
        width: 36; height: 36
        Accessible.name: text
        ToolTip.visible: hovered && text.length > 0
        ToolTip.text: text
        background: Rectangle {
            radius: action.circular ? width / 2 : 0
            color: action.primary ? Theme.primary : action.hovered ? Theme.surface : "transparent"
            border.width: action.activeFocus ? 1 : 0
            border.color: Theme.focus
        }
        contentItem: Item { ReviewIcon { name: action.glyph; ink: action.ink; size: action.primary ? 28 : 18; anchors.centerIn: parent } }
    }
    component Field: TextField {
        color: Theme.textPrimary
        placeholderTextColor: Theme.textSecondary
        selectionColor: Theme.primary
        selectedTextColor: Theme.textOnColor
        font.family: Theme.fontFamily
        font.pixelSize: 13
        selectByMouse: true
        height: 36
        leftPadding: 12
        background: Rectangle { color: Theme.surface; border.width: parent.activeFocus ? 1 : 0; border.color: Theme.focus }
    }
    component Mosaic: Item {
        property bool missing: false
        Grid {
            anchors.fill: parent
            columns: 2
            Repeater { model: [0, 1, 3, 5]; CoverArt { required property int modelData; width: parent.width / 2; height: width; pattern: modelData } }
            visible: !parent.missing
        }
        CoverArt { anchors.fill: parent; pattern: -1; visible: parent.missing }
    }
    component MenuLine: Button {
        id: line
        property string glyph: ""
        implicitWidth: 270
        implicitHeight: 38
        leftPadding: 14
        contentItem: Row {
            spacing: 12
            ReviewIcon { name: line.glyph; anchors.verticalCenter: parent.verticalCenter }
            Label { text: line.text; anchors.verticalCenter: parent.verticalCenter }
        }
        background: Rectangle { color: line.hovered || line.activeFocus ? Theme.selection : "transparent" }
    }
    component ReviewPopup: Popup {
        padding: 16
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
    }

    Rectangle {
        id: chrome
        width: parent.width; height: 32; color: Theme.chrome
        Label { x: 16; anchors.verticalCenter: parent.verticalCenter; text: "M"; color: Theme.primary; font.bold: true; font.pixelSize: 18 }
        Row { x: 54; anchors.verticalCenter: parent.verticalCenter; spacing: 22; Repeater { model: ["File", "Edit", "View", "Help"]; Label { required property string modelData; text: modelData; color: Theme.textSecondary; font.pixelSize: 12 } } }
        Row { anchors.right: parent.right; Repeater { model: ["win-minimize", "win-maximize", "win-close"]; Action { required property string modelData; glyph: modelData; width: 46; height: 32; onClicked: if (modelData === "win-close") root.close() } } }
    }
    Rectangle {
        id: rail
        y: chrome.height; width: 48; height: root.height - y; color: Theme.chrome
        Column { y: 10; spacing: 8; Repeater { model: ["explorer", "playlists", "convert", "tasks", "plugins"]; Action { required property string modelData; x: 6; glyph: modelData; text: modelData; active: modelData === "playlists" } } }
        Action { x: 6; anchors.bottom: parent.bottom; anchors.bottomMargin: 18; glyph: "settings"; text: "Settings"; onClicked: root.feedback = "Creator name is shared in Settings → General" }
    }
    Rectangle {
        id: sidebar
        x: rail.width; y: chrome.height; width: root.sidebarWidth; height: root.height - y
        color: Theme.sidebar
        visible: width > 0
        Label { x: 18; y: 17; text: "Playlists"; font.weight: Font.DemiBold }
        Action { objectName: "createPlaylistButton"; anchors.right: parent.right; anchors.rightMargin: 10; y: 7; glyph: "plus"; text: "Create or import"; onClicked: createMenu.open() }
        Column {
            x: 8; y: 60; width: parent.width - 16; spacing: 2
            Repeater {
                model: [
                    { name: "Liked tracks", summary: "2 tracks", kind: "liked", depth: 0 },
                    { name: "Night drive", summary: "6 tracks · 1 unavailable", kind: "pinned", depth: 0 },
                    { name: "Bass crates", summary: "", kind: "folder", depth: 0 },
                    { name: "Bass essentials", summary: "28 tracks", kind: "playlist", depth: 1 },
                    { name: "Sets", summary: "", kind: "folder", depth: 1 },
                    { name: "Opening", summary: "", kind: "folder", depth: 2 },
                    { name: "Warm-up", summary: "12 tracks", kind: "playlist", depth: 3 },
                    { name: "Late set", summary: "19 tracks", kind: "playlist", depth: 2 }
                ]
                delegate: ItemDelegate {
                    id: sideEntry
                    required property var modelData
                    padding: 0
                    readonly property bool branch: modelData.kind === "folder"
                    readonly property bool current: modelData.name === root.playlistName
                    visible: modelData.depth === 0 || (root.folderOpen && (modelData.depth < 3 || root.nestedOpen))
                    width: parent.width; height: visible ? branch ? 36 : 58 : 0
                    Accessible.name: modelData.name
                    background: Rectangle { color: sideEntry.current ? Theme.selection : sideEntry.hovered ? Theme.surface : "transparent" }
                    contentItem: Item {
                        readonly property int indent: sideEntry.modelData.depth * 12
                        Mosaic { x: parent.indent + 6; y: 7; width: 38; height: 38; visible: !sideEntry.branch && sideEntry.modelData.kind !== "liked" }
                        Rectangle { x: 6; y: 7; width: 38; height: 38; color: Theme.surface; visible: sideEntry.modelData.kind === "liked"; ReviewIcon { anchors.centerIn: parent; name: "heart-filled"; size: 20 } }
                        ReviewIcon { x: parent.indent + 5; anchors.verticalCenter: parent.verticalCenter; name: "chevron-down"; size: 14; visible: sideEntry.branch }
                        ReviewIcon { x: parent.indent + 24; anchors.verticalCenter: parent.verticalCenter; name: "folder"; size: 17; visible: sideEntry.branch }
                        Label { x: parent.indent + 54; y: sideEntry.branch ? 6 : 8; width: parent.width - x - 18; text: sideEntry.modelData.name; color: sideEntry.current ? Theme.primary : Theme.textPrimary; font.pixelSize: 13 }
                        Label { x: parent.indent + 54; y: 30; width: parent.width - x - 8; text: sideEntry.modelData.summary; color: Theme.textSecondary; font.pixelSize: 11; visible: !sideEntry.branch }
                        ReviewIcon { anchors.right: parent.right; anchors.rightMargin: 2; y: 9; name: "pin"; size: 14; visible: sideEntry.modelData.kind === "pinned" && root.pinned }
                    }
                    onClicked: {
                        if (modelData.kind === "folder") {
                            if (modelData.depth === 0) root.folderOpen = !root.folderOpen
                            else root.nestedOpen = !root.nestedOpen
                        } else {
                            root.scene = modelData.kind === "liked" ? "liked" : "playlist"
                            root.playlistName = modelData.name
                        }
                    }
                }
            }
        }
    }
    Rectangle {
        id: tabs
        x: rail.width + sidebar.width; y: chrome.height; width: root.width - x; height: 36; color: Theme.sidebar
        Row { height: parent.height
            MenuLine { width: 136; height: 36; text: "Music library"; glyph: "folder"; onClicked: root.feedback = "Audio folder pages keep their existing header" }
            Rectangle { width: 174; height: 36; color: Theme.editor; Rectangle { width: parent.width; height: 1; color: Theme.primary } ReviewIcon { x: 12; y: 10; name: "playlists"; ink: Theme.primary; size: 16 } Label { x: 38; y: 8; width: 105; text: root.playlistName; font.pixelSize: 13 } Action { x: 142; height: 36; width: 28; glyph: "close"; text: "Close tab" } }
        }
        Action { anchors.right: parent.right; glyph: "split"; text: "Split editor" }
    }
    Item {
        id: page
        x: tabs.x; y: tabs.y + tabs.height; width: root.width - x; height: root.height - y - 24
        readonly property int padding: 28
        readonly property int coverSize: width < 740 ? 164 : 208
        Item {
            id: header
            width: parent.width; height: page.coverSize + 122
            Mosaic { id: heroCover; x: page.padding; y: 24; width: page.coverSize; height: width; missing: root.emptyPlaylist }
            Column {
                x: heroCover.x + heroCover.width + 28; y: width < 420 ? 30 : 56
                width: header.width - x - page.padding - 36; spacing: 14
                Label { width: parent.width; text: root.playlistName; font.pixelSize: page.width < 740 ? 36 : 52; font.weight: Font.Bold; maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight }
                Label { width: parent.width; text: root.emptyPlaylist ? "Add a description" : root.scene === "liked" ? "Your favourites, saved in MTEE." : root.description; color: Theme.textSecondary; wrapMode: Text.Wrap; maximumLineCount: 2; font.pixelSize: 13 }
                Label { width: parent.width; text: "Local creator  ·  " + (root.emptyPlaylist ? "0 tracks · 0 min" : root.scene === "liked" ? "2 tracks · 8 min" : "6 tracks · 26 min · 1 unavailable"); color: Theme.textSecondary; wrapMode: Text.Wrap; maximumLineCount: 2; font.pixelSize: 12 }
            }
            Action { anchors.right: parent.right; anchors.rightMargin: 22; y: 24; glyph: "more"; text: "Playlist actions"; onClicked: detailsMenu.open() }
            Item {
                id: toolbar
                x: page.padding; y: heroCover.y + heroCover.height + 20; width: header.width - 2 * page.padding; height: 56
                Action { objectName: "playlistPlayButton"; glyph: root.playing ? "pause" : "play"; text: "Play visible tracks"; primary: true; circular: true; width: 56; height: 56; enabled: root.playableCount > 0; opacity: enabled ? 1 : 0.35; onClicked: { root.playing = !root.playing; root.playingId = root.visibleTracks.find(t => !t.missing).id; root.feedback = "Playing " + root.playableCount + " visible, available tracks" } }
                Action { x: 72; y: 10; glyph: "shuffle"; text: "Shuffle visible tracks"; active: root.shuffle; enabled: root.playableCount > 0; opacity: enabled ? 1 : 0.35; onClicked: { root.shuffle = !root.shuffle; root.feedback = "Shuffle applies to visible, available tracks" } }
                MenuLine { x: 128; y: 10; width: 155; height: 36; visible: page.width > 900; glyph: "list"; text: root.sortMode; onClicked: root.sortMode = root.sortMode === "Custom order" ? "Title A–Z" : "Custom order" }
                Row {
                    id: viewActions
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                    Item {
                        objectName: "playlistSearchReveal"
                        width: root.searchOpen ? Math.min(240, page.width - 310) : 0; height: 36; clip: true
                        Behavior on width { NumberAnimation { duration: 190; easing.type: Easing.OutExpo } }
                        Field { objectName: "playlistSearchField"; id: searchField; anchors.right: parent.right; width: Math.min(240, page.width - 310); placeholderText: "Search this playlist"; text: root.query; onTextEdited: root.query = text; Keys.onEscapePressed: { root.searchOpen = false; page.forceActiveFocus() } }
                    }
                    Action { objectName: "playlistSearchButton"; glyph: "search"; text: "Search this playlist"; active: root.query.length > 0 || root.searchOpen; onClicked: { root.searchOpen = !root.searchOpen; if (root.searchOpen) searchField.forceActiveFocus() } }
                    Action { glyph: "list"; text: "List"; active: !root.artwork; onClicked: root.artwork = false }
                    Action { glyph: "grid"; text: "Artwork"; active: root.artwork; onClicked: root.artwork = true }
                    Action { glyph: "settings"; text: "Choose columns"; onClicked: columnMenu.open() }
                }
            }
            Rectangle { x: page.padding; anchors.bottom: parent.bottom; width: parent.width - 2 * page.padding; height: 1; color: Theme.separator }
        }
        Flickable {
            id: table
            anchors.top: header.bottom; anchors.bottom: island.top; anchors.bottomMargin: 16
            width: parent.width; clip: true; contentWidth: Math.max(width, 820)
            contentHeight: Math.max(height, root.artwork ? Math.ceil(root.visibleTracks.length / Math.max(1, Math.floor((width - 56) / 166))) * 202 + 40 : 44 + root.visibleTracks.length * 58 + 20)
            flickableDirection: Flickable.HorizontalAndVerticalFlick; boundsBehavior: Flickable.StopAtBounds
            readonly property int titleWidth: contentWidth - 650
            ScrollBar.horizontal: ThinScrollBar {}
            ScrollBar.vertical: ThinScrollBar {}
            Column {
                width: table.contentWidth; visible: !root.artwork
                Item {
                    width: parent.width; height: 44
                    Row { x: page.padding; anchors.verticalCenter: parent.verticalCenter
                        Label { width: table.titleWidth; text: "Title"; color: Theme.textSecondary; font.pixelSize: 12 }
                        Label { width: 146; text: "Artist"; color: Theme.textSecondary; font.pixelSize: 12 }
                        Label { width: 120; text: "Album"; color: Theme.textSecondary; font.pixelSize: 12 }
                        Label { width: 60; text: "BPM"; color: Theme.textSecondary; font.pixelSize: 12 }
                        Label { width: 55; text: "Key"; color: Theme.textSecondary; font.pixelSize: 12 }
                        ReviewIcon { name: "clock"; size: 16 }
                    }
                }
                Repeater {
                    model: root.visibleTracks
                    delegate: ItemDelegate {
                        id: trackRow
                        required property var modelData
                        padding: 0
                        width: table.contentWidth; height: 58
                        objectName: "reviewTrack_" + modelData.id
                        Accessible.name: modelData.title + (modelData.missing ? ", file unavailable" : "")
                        background: Rectangle { color: trackRow.hovered ? Theme.surface : "transparent" }
                        contentItem: Item {
                            x: page.padding
                            Row { x: page.padding; anchors.verticalCenter: parent.verticalCenter
                                Item { width: table.titleWidth; height: 44
                                    CoverArt { y: 2; width: 40; height: 40; pattern: trackRow.modelData.cover; opacity: trackRow.modelData.missing ? 0.45 : 1 }
                                    Label { x: 54; y: trackRow.modelData.missing ? 2 : 12; width: parent.width - 66; text: trackRow.modelData.title; color: trackRow.modelData.missing ? Theme.textSecondary : root.playingId === trackRow.modelData.id ? Theme.primary : Theme.textPrimary }
                                    Button { x: 54; y: 22; width: Math.max(0, parent.width - 66); visible: !!trackRow.modelData.missing; text: table.titleWidth < 260 ? "Locate file" : "File unavailable · Locate file"; height: 22; padding: 0; contentItem: Label { text: parent.text; color: Theme.textSecondary; font.pixelSize: 11 } background: Item {} onClicked: locate.open() }
                                }
                                Label { width: 146; height: 44; verticalAlignment: Text.AlignVCenter; text: trackRow.modelData.artist; color: Theme.textSecondary; font.pixelSize: 13 }
                                Label { width: 120; height: 44; verticalAlignment: Text.AlignVCenter; text: trackRow.modelData.album; color: Theme.textSecondary; font.pixelSize: 13 }
                                Label { width: 60; height: 44; verticalAlignment: Text.AlignVCenter; text: trackRow.modelData.bpm; color: Theme.textSecondary; font.pixelSize: 12 }
                                Item { width: 55; height: 44; KeyBadge { anchors.verticalCenter: parent.verticalCenter; key: trackRow.modelData.key; camelot: trackRow.modelData.key; visible: !trackRow.modelData.missing } Label { y: 13; text: "—"; visible: !!trackRow.modelData.missing; color: Theme.textSecondary } }
                                Label { width: 55; height: 44; verticalAlignment: Text.AlignVCenter; text: trackRow.modelData.length; color: Theme.textSecondary; font.pixelSize: 12 }
                                Action { objectName: "likeTrack_" + trackRow.modelData.id; y: 4; width: 28; glyph: root.likes[trackRow.modelData.id] ? "heart-filled" : "heart"; text: root.likes[trackRow.modelData.id] ? "Unlike track" : "Like track"; onClicked: root.toggleLike(trackRow.modelData.id) }
                                Action { objectName: "addTrack_" + trackRow.modelData.id; y: 4; width: 30; glyph: "plus"; text: "Add to playlist"; onClicked: addMenu.open() }
                            }
                        }
                        onDoubleClicked: if (!modelData.missing) { root.playingId = modelData.id; root.playing = true }
                    }
                }
            }
            Grid {
                x: page.padding; y: 22; columns: Math.max(1, Math.floor((table.width - 56) / 166)); spacing: 20; visible: root.artwork
                Repeater { model: root.visibleTracks; Column { required property var modelData; width: 146; spacing: 8; CoverArt { width: 146; height: 146; pattern: modelData.cover } Label { width: 146; text: modelData.title; font.pixelSize: 13 } Label { width: 146; text: modelData.artist; color: Theme.textSecondary; font.pixelSize: 12 } } }
            }
            Column {
                x: page.padding; y: 56; width: table.width - 2 * page.padding; spacing: 14; visible: root.visibleTracks.length === 0
                Label { width: parent.width; text: root.emptyPlaylist ? "Make it your own" : "No matching tracks"; font.pixelSize: 24; font.weight: Font.DemiBold }
                Label { width: parent.width; text: root.emptyPlaylist ? "Add tracks from your library with +, or drag them into this playlist." : "Try a different title, artist or album."; color: Theme.textSecondary; wrapMode: Text.Wrap }
                TextButton { text: root.emptyPlaylist ? "Browse library" : "Clear search"; kind: "ghost"; onClicked: { if (!root.emptyPlaylist) root.query = ""; else root.feedback = "Select tracks in an audio folder, then use + or drag to this playlist" } }
            }
        }
        Rectangle {
            id: island
            x: page.padding; anchors.bottom: parent.bottom; anchors.bottomMargin: 20
            width: parent.width - 2 * page.padding; height: 70; color: Theme.surface
            CoverArt { x: 12; y: 13; width: 44; height: 44; pattern: 0 }
            Label { x: 70; y: 14; width: 180; text: "Control (Original Mix)"; font.pixelSize: 13 }
            Label { x: 70; y: 36; text: "Northline"; color: Theme.textSecondary; font.pixelSize: 12 }
            Row { anchors.horizontalCenter: parent.horizontalCenter; y: 7; spacing: 8; visible: parent.width > 680; Action { glyph: "shuffle"; active: root.shuffle } Action { glyph: "previous" } Action { glyph: root.playing ? "pause" : "play"; primary: true; onClicked: root.playing = !root.playing } Action { glyph: "next" } Action { glyph: "repeat" } }
            Rectangle { x: Math.max(270, parent.width * 0.30); y: 56; width: parent.width * 0.40; height: 3; color: Theme.separator; visible: parent.width > 680; Rectangle { width: parent.width * 0.28; height: 3; color: Theme.textSecondary } }
            Row { anchors.right: parent.right; anchors.rightMargin: 12; y: 18; Action { glyph: "queue" } Action { glyph: "volume" } Action { glyph: "fullscreen" } }
        }
    }
    Label { x: tabs.x + 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 5; width: root.width - x - 12; text: root.feedback; color: Theme.textSecondary; font.pixelSize: 10 }

    ReviewPopup {
        id: createMenu
        x: rail.width + Math.max(8, sidebar.width - width - 8); y: 78; width: 282; height: 162
        contentItem: Column { spacing: 4
            MenuLine { text: "New playlist"; glyph: "plus"; width: parent.width; onClicked: { root.emptyPlaylist = true; root.playlistName = "New playlist"; createMenu.close() } }
            MenuLine { text: "New folder"; glyph: "folder"; width: parent.width; onClicked: { root.feedback = "New folder can be renamed and nested in the sidebar"; createMenu.close() } }
            MenuLine { text: "Import playlist…"; glyph: "playlists"; width: parent.width; onClicked: { createMenu.close(); transfer.mode = "import"; transfer.open() } }
        }
    }
    ReviewPopup {
        id: addMenu
        objectName: "reviewAddMenu"
        x: root.width - width - 32; y: 192; width: Math.min(350, root.width - 40); height: 520
        contentItem: Column { spacing: 12
            Label { text: "Add to playlist"; font.weight: Font.DemiBold }
            Field { id: menuSearch; objectName: "reviewPlaylistMenuSearch"; width: parent.width; placeholderText: "Search playlists"; leftPadding: 36; Icon { x: 10; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 16; color: Theme.textSecondary } }
            MenuLine { text: "New playlist"; glyph: "plus"; width: parent.width; onClicked: root.feedback = "Create a named playlist with the selected tracks; keep this menu open" }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Repeater {
                model: [true, false]
                delegate: Column {
                    required property bool modelData
                    width: parent.width; spacing: 4
                    Label { text: parent.modelData ? "Saved in" : "Recently updated"; color: Theme.textSecondary; font.pixelSize: 12; font.weight: Font.DemiBold }
                    Repeater {
                        model: root.destinations.filter(p => !!root.membership[p.id] === modelData && p.name.toLowerCase().indexOf(menuSearch.text.toLowerCase()) >= 0)
                        delegate: ItemDelegate {
                            id: destination
                            required property var modelData
                            objectName: "reviewDestination_" + modelData.id
                            width: parent.width; height: 59
                            Accessible.name: modelData.name
                            Accessible.checkable: true
                            Accessible.checked: !!root.membership[modelData.id]
                            background: Rectangle { color: destination.hovered || destination.activeFocus ? Theme.selection : "transparent" }
                            contentItem: Item {
                                CoverArt { y: 5; width: 42; height: 42; pattern: destination.modelData.cover }
                                Label { x: 54; y: 7; width: parent.width - 84; text: destination.modelData.name }
                                Label { x: 54; y: 30; width: parent.width - 84; text: destination.modelData.info; color: Theme.textSecondary; font.pixelSize: 11 }
                                Rectangle { anchors.right: parent.right; y: 16; width: 20; height: 20; radius: 10; color: root.membership[destination.modelData.id] ? Theme.primary : "transparent"; border.width: root.membership[destination.modelData.id] ? 0 : 1; border.color: Theme.textSecondary; Icon { anchors.centerIn: parent; name: "check"; color: Theme.textOnColor; size: 14; visible: !!root.membership[destination.modelData.id] } }
                            }
                            onClicked: root.toggleMember(modelData.id)
                        }
                    }
                }
            }
            TextButton { anchors.right: parent.right; text: "Close"; kind: "ghost"; onClicked: addMenu.close() }
        }
    }
    ReviewPopup {
        id: detailsMenu
        x: root.width - width - 24; y: 126; width: 282; height: 256
        contentItem: Column { spacing: 4
            MenuLine { text: "Edit details…"; glyph: "info"; width: parent.width; onClicked: { root.feedback = "Edit name, description and local cover; mosaic is the default"; detailsMenu.close() } }
            MenuLine { text: root.pinned ? "Unpin playlist" : "Pin playlist"; glyph: "pin"; width: parent.width; onClicked: { root.pinned = !root.pinned; detailsMenu.close() } }
            MenuLine { text: "Duplicate playlist"; glyph: "playlists"; width: parent.width; onClicked: { root.playlistName += " (copy)"; detailsMenu.close() } }
            MenuLine { text: "Export playlist…"; glyph: "folder"; width: parent.width; onClicked: { detailsMenu.close(); transfer.mode = "export"; transfer.open() } }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            MenuLine { text: "Delete playlist…"; glyph: "close"; width: parent.width; onClicked: { root.feedback = "Confirmation required. Audio files are kept."; detailsMenu.close() } }
        }
    }
    ReviewPopup {
        id: columnMenu
        x: root.width - width - 28; y: page.y + page.coverSize + 114; width: 250; height: 324
        contentItem: Column { spacing: 7
            Label { text: "Playlist columns"; font.weight: Font.DemiBold }
            Repeater { model: ["Title", "Artist", "Album", "BPM", "Key", "Duration"]; CheckBox { id: columnChoice; required property string modelData; text: modelData; checked: true; height: 31; font.family: Theme.fontFamily; palette.windowText: Theme.textPrimary; palette.highlight: Theme.primary; palette.base: Theme.surface; indicator: Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 20; height: 20; color: Theme.surface; border.width: 1; border.color: Theme.textSecondary; Icon { anchors.centerIn: parent; name: "check"; color: Theme.primary; size: 16; visible: columnChoice.checked } } } }
            Label { width: parent.width; text: "Shared by all playlists"; font.pixelSize: 11; color: Theme.textSecondary }
            TextButton { text: "Reset columns"; kind: "ghost"; onClicked: root.feedback = "Reset only the playlist column profile" }
        }
    }
    ReviewPopup {
        id: transfer
        property string mode: "export"
        x: (root.width - width) / 2; y: 200; width: Math.min(470, root.width - 48); height: mode === "export" ? 292 : 310
        contentItem: Column { spacing: 18
            Label { text: transfer.mode === "export" ? "Export playlist" : "Import playlist"; font.pixelSize: 23; font.weight: Font.DemiBold }
            Label { width: parent.width; text: transfer.mode === "export" ? "Night drive · 6 tracks · 1 unavailable" : "Choose a .mteeplaylist file or a complete ZIP."; color: Theme.textSecondary; wrapMode: Text.Wrap }
            RadioButton { id: withAudio; visible: transfer.mode === "export"; text: "Complete ZIP with audio files"; checked: root.exportKind === "zip"; font.family: Theme.fontFamily; palette.windowText: Theme.textPrimary; onClicked: root.exportKind = "zip"; indicator: Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; radius: 9; color: "transparent"; border.width: 1; border.color: withAudio.checked ? Theme.primary : Theme.textSecondary; Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: Theme.primary; visible: withAudio.checked } } }
            RadioButton { id: playlistOnly; visible: transfer.mode === "export"; text: "Playlist only (.mteeplaylist)"; checked: root.exportKind === "playlist"; font.family: Theme.fontFamily; palette.windowText: Theme.textPrimary; onClicked: root.exportKind = "playlist"; indicator: Rectangle { x: 0; anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; radius: 9; color: "transparent"; border.width: 1; border.color: playlistOnly.checked ? Theme.primary : Theme.textSecondary; Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: Theme.primary; visible: playlistOnly.checked } } }
            Field { width: parent.width; visible: transfer.mode === "import"; placeholderText: "Choose playlist file…" }
            Label { width: parent.width; text: transfer.mode === "export" ? "Unavailable entries keep their place in the exported playlist." : "For a ZIP, choose where to extract the audio. MTEE adds that folder to your library and restores the playlist."; font.pixelSize: 12; color: Theme.textSecondary; wrapMode: Text.Wrap }
            Row { anchors.right: parent.right; spacing: 10; TextButton { text: "Cancel"; kind: "ghost"; onClicked: transfer.close() } TextButton { text: transfer.mode === "export" ? "Choose destination…" : "Choose file…"; kind: "primary"; onClicked: { root.feedback = "Review prototype: no file dialog, audio or database mutation"; transfer.close() } } }
        }
    }
    ReviewPopup {
        id: locate
        x: (root.width - width) / 2; y: 235; width: Math.min(500, root.width - 48); height: 280
        contentItem: Column { spacing: 18
            Label { text: "Locate missing track"; font.pixelSize: 23; font.weight: Font.DemiBold }
            Label { width: parent.width; text: "Afterlight (Extended Mix) · Northline"; wrapMode: Text.Wrap }
            Label { width: parent.width; text: "Choose the same recording from your library or select its file. Its position in the playlist is preserved."; color: Theme.textSecondary; font.pixelSize: 13; wrapMode: Text.Wrap }
            MenuLine { text: "Afterlight (Extended Mix) · FLAC"; glyph: "music"; width: parent.width; onClicked: root.feedback = "Candidate chosen; the real service will verify and save the association" }
            Row { anchors.right: parent.right; spacing: 10; TextButton { text: "Cancel"; kind: "ghost"; onClicked: locate.close() } TextButton { text: "Choose local file…"; kind: "primary"; onClicked: locate.close() } }
        }
    }
}
