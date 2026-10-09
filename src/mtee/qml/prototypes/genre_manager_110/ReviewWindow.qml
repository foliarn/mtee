import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Mtee

Window {
    id: root
    objectName: "genreManager110Review"
    width: Math.min(1440, Screen.desktopAvailableWidth - 32)
    height: Math.min(900, Screen.desktopAvailableHeight - 32)
    minimumWidth: 1100
    minimumHeight: 650
    visible: true
    title: "MTEE — Genre Manager review"
    color: Theme.chrome
    property string creationParent: ""
    property bool creatingGenre: false
    property string selectedGenre: "Deep House"
    property string folderGenre: "House"
    function openSourcePicker() { sourcePicker.open() }
    function openFolderTagPopup() { folderTagPopup.open() }

    component ReviewButton: Button {
        id: action
        property bool primary: false
        property bool selected: false
        property bool danger: false
        property bool leftAligned: false
        implicitHeight: 34
        implicitWidth: Math.max(78, label.implicitWidth + 24)
        background: Rectangle {
            color: action.primary ? Theme.primary
                : action.selected ? Theme.selection
                : action.hovered ? "#303036" : action.leftAligned ? "transparent" : Theme.surface
            border.width: action.activeFocus ? 1 : 0
            border.color: Theme.focus
            radius: Theme.radius
        }
        leftPadding: 0
        rightPadding: 0
        topPadding: 0
        bottomPadding: 0
        contentItem: Item {
            implicitWidth: label.implicitWidth + 24
            implicitHeight: 34
            Text {
                id: label
                anchors.fill: parent
                anchors.leftMargin: action.leftAligned ? 12 : 0
                text: action.text
                color: !action.enabled ? Theme.textMuted : action.primary ? Theme.textOnColor : action.danger ? Theme.danger : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.weight: action.primary ? Font.Bold : Font.Medium
                horizontalAlignment: action.leftAligned ? Text.AlignLeft : Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }
    }

    component ReviewField: TextField {
        implicitHeight: 34
        color: Theme.textPrimary
        placeholderTextColor: Theme.textSecondary
        selectByMouse: true
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
        verticalAlignment: TextInput.AlignVCenter
        background: Rectangle {
            color: Theme.surface
            border.width: parent.activeFocus ? 1 : 0
            border.color: Theme.focus
        }
    }

    Shortcut {
        sequence: "Ctrl+Z"
        enabled: !(root.activeFocusItem instanceof TextInput)
        onActivated: prototype.undo()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.titleBarHeight
            color: Theme.chrome
            RowLayout {
                anchors.fill: parent
                spacing: 18
                Text {
                    text: "M"
                    color: Theme.primary
                    Layout.preferredWidth: Theme.activityBarWidth
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.family: Theme.fontFamily
                    font.pixelSize: 16
                    font.weight: Font.ExtraBold
                }
                Repeater {
                    model: ["File", "Edit", "View", "Help"]
                    Text {
                        required property string modelData
                        text: modelData
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: "−"; color: Theme.textSecondary; font.pixelSize: 16 }
                Text { text: "□"; color: Theme.textSecondary; font.pixelSize: 16 }
                Text { Layout.rightMargin: 18; text: "×"; color: Theme.textSecondary; font.pixelSize: 16 }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.preferredWidth: Theme.activityBarWidth
                Layout.fillHeight: true
                color: Theme.chrome
                Column {
                    width: parent.width
                    Repeater {
                        model: ["explorer", "playlists", "artists", "convert", "tasks", "plugins"]
                        Item {
                            required property string modelData
                            width: Theme.activityBarWidth
                            height: Theme.activityBarWidth
                            Rectangle { visible: modelData === "plugins"; width: 2; height: parent.height; color: Theme.primary }
                            Icon { anchors.centerIn: parent; name: modelData; size: 24; color: modelData === "plugins" ? Theme.textPrimary : Theme.textMuted }
                            MouseArea { anchors.fill: parent; onClicked: prototype.setSection("Plugins") }
                        }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: Theme.sidebarWidth
                Layout.fillHeight: true
                color: Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 7
                    Text {
                        text: "PLUGINS"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "‹  All plugins"
                        leftAligned: true
                        onClicked: prototype.setSection("Plugins")
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Text {
                        text: "GENRE MANAGER"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Classify"
                        leftAligned: true
                        selected: prototype.section === "Classify"
                        onClicked: prototype.setSection("Classify")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Genres & tags"
                        leftAligned: true
                        selected: prototype.section === "Genres"
                        onClicked: prototype.setSection("Genres")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Uncertain"
                        leftAligned: true
                        selected: prototype.section === "Uncertain"
                        onClicked: prototype.setSection("Uncertain")
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Text {
                        text: "Interaction to compare"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Selection, then assign"
                        leftAligned: true
                        selected: prototype.variant === "selection"
                        onClicked: prototype.setVariant("selection")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Brush"
                        leftAligned: true
                        selected: prototype.variant === "brush"
                        onClicked: prototype.setVariant("brush")
                    }
                    Item { Layout.fillHeight: true }
                    Text {
                        Layout.fillWidth: true
                        text: "No audio tags or personal library files are changed by this review."
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.editor

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Theme.tabHeight
                        color: Theme.sidebar
                        Rectangle {
                            width: 190; height: parent.height; color: Theme.editor
                            Rectangle { width: parent.width; height: 1; color: Theme.primary }
                            Row {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                spacing: 8
                                Icon { anchors.verticalCenter: parent.verticalCenter; name: "plugins"; size: 16; color: Theme.primary }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Genre Manager"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 13
                                }
                            }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        sourceComponent: prototype.section === "Classify" ? classifyPage
                            : prototype.section === "Genres" ? genresPage
                            : prototype.section === "Uncertain" ? uncertainPage
                            : prototype.section === "Organize" ? organizePage : pluginsPage
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: prototype.error ? 72 : 52
                        color: prototype.error ? "#3A1D24" : Theme.sidebar
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 20
                            anchors.rightMargin: 20
                            spacing: 12
                            Text {
                                Layout.fillWidth: true
                                text: prototype.error || prototype.message
                                color: prototype.error ? Theme.danger : Theme.textSecondary
                                wrapMode: Text.WordWrap
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                            }
                            ReviewButton {
                                visible: !!prototype.error
                                text: "Retry"
                                onClicked: prototype.retry()
                            }
                            ReviewButton {
                                visible: prototype.section === "Organize"
                                text: "Move files"
                                enabled: false
                            }
                            ReviewButton {
                                text: "Undo"
                                onClicked: prototype.undo()
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.islandHeight
            color: Theme.chrome
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                spacing: 12
                Rectangle { width: 48; height: 48; color: Theme.surface; border.color: Theme.separator }
                ColumnLayout {
                    Layout.preferredWidth: Math.min(230, root.width * 0.22)
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        text: prototype.playingTitle || "No track playing"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                        elide: Text.ElideRight
                    }
                    Text { text: "Synthetic audio"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                }
                Item { Layout.fillWidth: true }
                ColumnLayout {
                    Layout.preferredWidth: Math.min(510, root.width * 0.43)
                    spacing: 7
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 18
                        Icon { name: "shuffle"; size: 20; color: Theme.primary }
                        Icon { name: "previous"; size: 20; color: Theme.textSecondary }
                        Rectangle {
                            width: 40; height: 40; radius: 20
                            color: prototype.playingTitle ? Theme.primary : Theme.surface
                            Icon { anchors.centerIn: parent; name: prototype.playingTitle ? "pause" : "play"; size: 20; color: prototype.playingTitle ? Theme.textOnColor : Theme.textSecondary }
                            MouseArea { anchors.fill: parent; onClicked: prototype.togglePause() }
                        }
                        Icon { name: "next"; size: 20; color: Theme.textSecondary }
                        Icon { name: "repeat"; size: 20; color: Theme.primary }
                    }
                    Rectangle { Layout.fillWidth: true; height: 3; color: Theme.selection }
                }
                Item { Layout.fillWidth: true }
                Icon { name: "queue"; size: 20; color: Theme.textSecondary }
                Icon { name: "volume"; size: 20; color: Theme.textSecondary }
                Rectangle { width: 55; height: 3; color: Theme.textMuted }
                Icon { name: "fullscreen"; size: 20; color: Theme.textSecondary }
            }
        }
    }

    Component {
        id: pluginsPage
        ColumnLayout {
            anchors.margins: 24
            spacing: 16
            Text {
                text: "Available plugins"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 18
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 86
                color: Theme.surface
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    Text {
                        text: "Genre Manager\nClassify, review, and plan file organization."
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 14
                    }
                    Item { Layout.fillWidth: true }
                    ReviewButton { text: "Open"; primary: true; onClicked: prototype.setSection("Classify") }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }

    Component {
        id: classifyPage
        ColumnLayout {
            spacing: 0
            Item {
                Layout.fillWidth: true; Layout.preferredHeight: 142
                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 32; anchors.rightMargin: 32
                    anchors.topMargin: 16; anchors.bottomMargin: 12
                    spacing: 6
                    Text { text: prototype.sourceKind === "folder" ? "FOLDER" : "PLAYLIST"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; font.weight: Font.Bold }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 12
                        Button {
                            objectName: "sourceButton"
                            leftPadding: 0; rightPadding: 0; topPadding: 0; bottomPadding: 0
                            implicitWidth: Math.min(355, Math.max(160, prototype.sourceName.length * 19 + 38))
                            implicitHeight: 39
                            onClicked: sourcePicker.open()
                            background: Rectangle { color: parent.hovered ? Theme.surface : "transparent" }
                            contentItem: Text {
                                text: prototype.sourceName + "  ▾"
                                color: Theme.textPrimary; font.family: Theme.displayFontFamily
                                font.pixelSize: 28; font.weight: Font.Bold
                                horizontalAlignment: Text.AlignLeft; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                            }
                        }
                        Text { text: prototype.totalCount + " titles · " + prototype.reviewedCount + " reviewed"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter }
                        Item { Layout.fillWidth: true }
                        ReviewField { Layout.preferredWidth: root.width < 1200 ? 180 : 240; placeholderText: "Search this source"; onTextChanged: prototype.setSearch(text) }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        ReviewButton { visible: prototype.sourceKind === "folder"; text: "Tag folder songs…"; onClicked: { root.folderGenre = "House"; folderTagPopup.open() } }
                        ReviewButton { visible: prototype.sourceKind === "folder"; text: "Include subfolders"; selected: prototype.includeSubfolders; onClicked: prototype.toggleSubfolders() }
                        ReviewButton { text: prototype.variant === "brush" ? "Brush: " + prototype.brushLabel : "Assign genre…"; onClicked: genrePicker.open() }
                        ReviewButton { text: "Tag…"; onClicked: tagPicker.open() }
                        Item { Layout.fillWidth: true }
                        ReviewButton { text: "All tracks"; selected: prototype.view === "All tracks"; onClicked: prototype.setView("All tracks") }
                        ReviewButton { text: "To review"; selected: prototype.view === "To review"; onClicked: prototype.setView("To review") }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 42
                Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 8
                Text { text: prototype.selectedCount + " selected"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                ReviewButton { text: "Mark " + prototype.selectedCount + " as reviewed"; primary: prototype.selectedCount > 0; onClicked: prototype.markReviewed() }
                ReviewButton { text: "Simulate save error"; onClicked: prototype.failNext() }
                Item { Layout.fillWidth: true }
                ReviewButton { text: "Organize files"; onClicked: prototype.preparePreview() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 42
                Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 10
                Text { text: "#"; Layout.preferredWidth: 30; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Title"; Layout.fillWidth: true; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Artist"; Layout.preferredWidth: root.width < 1250 ? 105 : 155; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Main genre"; Layout.preferredWidth: 120; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Tags"; Layout.preferredWidth: 80; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Reviewed"; Layout.preferredWidth: 66; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Item { Layout.preferredWidth: prototype.variant === "brush" ? 72 : 32 }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: trackList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: prototype.tracks
                boundsBehavior: Flickable.StopAtBounds
                delegate: Rectangle {
                    id: trackRow
                    required property var modelData
                    required property int index
                    width: trackList.width; height: 64
                    color: modelData.selected ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"
                    MouseArea { id: rowMouse; anchors.fill: parent; hoverEnabled: true; onClicked: (mouse) => prototype.selectTrack(trackRow.modelData.id, mouse.modifiers) }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 32; spacing: 10
                        Text { text: String(trackRow.index + 1); Layout.preferredWidth: 30; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter }
                        Rectangle {
                            width: 40; height: 40; color: ["#4D5833", "#36515C", "#594459", "#6A4A3B"][trackRow.index % 4]
                            Rectangle { anchors.centerIn: parent; width: 17; height: 17; radius: 9; color: "transparent"; border.color: Theme.primary }
                        }
                        Text { Layout.fillWidth: true; text: trackRow.modelData.title; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                        Text { Layout.preferredWidth: root.width < 1250 ? 105 : 155; text: trackRow.modelData.artist; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                        Text {
                            Layout.preferredWidth: 120
                            text: trackRow.modelData.genres.length ? trackRow.modelData.genres[0] : "—"
                            color: trackRow.modelData.genres.length ? Theme.textPrimary : Theme.textMuted
                            font.family: Theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter
                            ToolTip.visible: genreMouse.containsMouse && trackRow.modelData.genres.length > 1
                            ToolTip.text: trackRow.modelData.genres.join(" · ") + " — click to promote secondary"
                            MouseArea { id: genreMouse; anchors.fill: parent; hoverEnabled: true; onClicked: if (trackRow.modelData.genres.length > 1) prototype.makePrimary(trackRow.modelData.id, trackRow.modelData.genres[1]) }
                        }
                        Text { Layout.preferredWidth: 80; text: trackRow.modelData.tags.length ? trackRow.modelData.tags.join(", ") : "—"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                        Text { Layout.preferredWidth: 66; text: trackRow.modelData.reviewed ? "✓" : "—"; color: trackRow.modelData.reviewed ? Theme.primary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 15; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        Item {
                            visible: prototype.variant === "brush"; width: 32; height: 32
                            Icon { anchors.centerIn: parent; name: "plus"; size: 17; color: Theme.textSecondary }
                            MouseArea { anchors.fill: parent; onClicked: prototype.paintTrack(trackRow.modelData.id) }
                        }
                        Item {
                            width: 32; height: 32
                            Icon { anchors.centerIn: parent; name: "play"; size: 17; color: Theme.textSecondary }
                            MouseArea { anchors.fill: parent; onClicked: prototype.playTrack(trackRow.modelData.id) }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: genresPage
        ColumnLayout {
            spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 76
                Layout.leftMargin: 32; Layout.rightMargin: 32
                Text { text: "Genres & tags"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 28; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                ReviewButton {
                    objectName: "newRootGenreButton"
                    text: "New root genre"; primary: true
                    onClicked: { root.creationParent = ""; root.creatingGenre = true }
                }
            }
            RowLayout {
                visible: root.creatingGenre
                Layout.fillWidth: true; Layout.preferredHeight: 50
                Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 8
                Text { text: root.creationParent ? "New subgenre in " + root.creationParent : "New root genre"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                ReviewField { id: genreName; Layout.fillWidth: true; placeholderText: "Genre name"; onAccepted: { prototype.createGenre(text, root.creationParent); text = ""; root.creatingGenre = false } }
                ReviewButton { text: "Create"; onClicked: { prototype.createGenre(genreName.text, root.creationParent); genreName.text = ""; root.creatingGenre = false } }
                ReviewButton { text: "Cancel"; onClicked: root.creatingGenre = false }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            RowLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.leftMargin: 32; Layout.rightMargin: 32; spacing: 24
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8
                    ReviewField { id: genreSearch; Layout.fillWidth: true; placeholderText: "Search genres" }
                    Text { text: prototype.genreRows.length + " genres · scroll to browse"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    ListView {
                        id: genreList
                        objectName: "genreTreeList"
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        model: prototype.genreRows.filter(row => !genreSearch.text || row.name.toLowerCase().includes(genreSearch.text.toLowerCase()) || row.parent.toLowerCase().includes(genreSearch.text.toLowerCase()))
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: Rectangle {
                            id: genreRow
                            required property var modelData
                            width: genreList.width - 10; height: 36
                            color: root.selectedGenre === modelData.name ? Theme.selection : genreMouse.containsMouse ? Theme.surface : "transparent"
                            MouseArea { id: genreMouse; anchors.fill: parent; hoverEnabled: true; onClicked: root.selectedGenre = genreRow.modelData.name }
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: genreRow.modelData.root ? 8 : 30; anchors.rightMargin: 4; spacing: 8
                                Icon { name: genreRow.modelData.root ? "chevron-down" : "music"; size: 13; color: Theme.textSecondary }
                                Text { Layout.fillWidth: true; text: genreRow.modelData.name; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
                                Item {
                                    visible: genreRow.modelData.root
                                    objectName: "addSubgenreButton"
                                    width: 32; height: 32
                                    Icon { anchors.centerIn: parent; name: "plus"; size: 16; color: Theme.textSecondary }
                                    MouseArea { anchors.fill: parent; onClicked: { root.creationParent = genreRow.modelData.name; root.creatingGenre = true } }
                                }
                            }
                        }
                    }
                }
                Rectangle { width: 1; Layout.fillHeight: true; color: Theme.separator }
                ColumnLayout {
                    Layout.preferredWidth: 240; Layout.fillHeight: true; spacing: 10
                    Text { text: "SELECTED GENRE"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; font.weight: Font.Bold }
                    Text { text: root.selectedGenre; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 17; font.weight: Font.Bold }
                    ReviewField { id: renamedGenre; Layout.fillWidth: true; placeholderText: "Rename genre" }
                    RowLayout {
                        ReviewButton { text: "Rename"; onClicked: { prototype.renameGenre(root.selectedGenre, renamedGenre.text); if (renamedGenre.text) root.selectedGenre = renamedGenre.text; renamedGenre.text = "" } }
                        ReviewButton { text: "Archive"; onClicked: prototype.archiveGenre(root.selectedGenre) }
                    }
                    Text { visible: prototype.archivedGenres.length > 0; Layout.fillWidth: true; text: "Archived: " + prototype.archivedGenres.join(", "); color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap }
                    ReviewButton { visible: prototype.archivedGenres.length > 0; text: "Restore first"; onClicked: if (prototype.archivedGenres.length) prototype.restoreGenre(prototype.archivedGenres[0]) }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Text { text: "TAGS"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; font.weight: Font.Bold }
                    Text { Layout.fillWidth: true; text: prototype.tags.length ? prototype.tags.join(" · ") : "No tags yet"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; wrapMode: Text.WordWrap }
                    ReviewField { id: catalogueTag; Layout.fillWidth: true; placeholderText: "Tag name"; onAccepted: { prototype.createTag(text); text = "" } }
                    ReviewButton { text: "Create tag"; onClicked: { prototype.createTag(catalogueTag.text); catalogueTag.text = "" } }
                    Item { Layout.fillHeight: true }
                }
            }
        }
    }

    Component {
        id: uncertainPage
        ColumnLayout {
            anchors.margins: 24
            spacing: 14
            Text {
                text: "Artist contributions needing a decision"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 19
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                text: "A genre on a remix does not automatically become a genre of the original artist. These examples are illustrative; no artist record is changed."
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 13
            }
            Repeater {
                model: ["Madonna — UKG remix · remixer certain, original contribution withheld",
                    "Unknown flip — original credit ambiguous · attribution withheld",
                    "Two remixers — title and credits disagree · attribution withheld"]
                Rectangle {
                    required property string modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 54
                    color: Theme.surface
                    Text {
                        anchors.fill: parent
                        anchors.margins: 14
                        verticalAlignment: Text.AlignVCenter
                        text: parent.modelData
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: 13
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }

    Component {
        id: organizePage
        ColumnLayout {
            spacing: 0
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 78
                Layout.leftMargin: 32; Layout.rightMargin: 32
                Text { text: "Organize files"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 28; font.weight: Font.Bold }
                Item { Layout.fillWidth: true }
                ReviewButton { text: "Back to classify"; onClicked: prototype.setSection("Classify") }
            }
            Text {
                Layout.leftMargin: 32; Layout.rightMargin: 32; Layout.bottomMargin: 18
                text: prototype.preview.length + " reviewed tracks in this preview · No files are moved by this prototype"
                color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 42
                Layout.leftMargin: 32; Layout.rightMargin: 32
                Text { text: "#"; Layout.preferredWidth: 40; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Title"; Layout.fillWidth: true; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Current folder"; Layout.preferredWidth: 150; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Text { text: "Destination"; Layout.preferredWidth: 220; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: previewList
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true; boundsBehavior: Flickable.StopAtBounds
                model: prototype.preview
                delegate: Rectangle {
                    id: previewRow
                    required property var modelData
                    required property int index
                    width: previewList.width; height: 56; color: "transparent"
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 32
                        Text { text: String(previewRow.index + 1); Layout.preferredWidth: 40; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                        Text { text: previewRow.modelData.title; Layout.fillWidth: true; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14; elide: Text.ElideRight }
                        Text { text: previewRow.modelData["from"]; Layout.preferredWidth: 150; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight }
                        Text { text: previewRow.modelData.to; Layout.preferredWidth: 220; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight }
                    }
                }
            }
        }
    }

    Popup {
        id: sourcePicker
        objectName: "sourcePicker"
        property string tab: "folder"
        parent: Overlay.overlay
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        width: Math.min(560, root.width - 80); height: Math.min(350, root.height - 100)
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.sidebar; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 0
            Text { Layout.fillWidth: true; Layout.leftMargin: 22; Layout.topMargin: 18; Layout.bottomMargin: 14; text: "Choose a source"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 22; font.weight: Font.Bold }
            RowLayout {
                Layout.leftMargin: 22; Layout.rightMargin: 22; Layout.bottomMargin: 12
                ReviewButton { text: "Folders"; selected: sourcePicker.tab === "folder"; onClicked: sourcePicker.tab = "folder" }
                ReviewButton { text: "Playlists"; selected: sourcePicker.tab === "playlist"; onClicked: sourcePicker.tab = "playlist" }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: sourceList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: prototype.sourceOptions.filter(source => source.kind === sourcePicker.tab)
                delegate: Rectangle {
                    id: sourceRow
                    required property var modelData
                    width: sourceList.width; height: 68
                    color: sourceMouse.containsMouse ? Theme.surface : "transparent"
                    MouseArea { id: sourceMouse; anchors.fill: parent; hoverEnabled: true; onClicked: { prototype.setScenario(sourceRow.modelData.id); sourcePicker.close() } }
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 22; anchors.rightMargin: 22
                        Icon { name: sourcePicker.tab === "folder" ? "folder" : "playlists"; size: 18; color: Theme.primary }
                        ColumnLayout {
                            Layout.preferredWidth: 220; spacing: 2
                            Text { text: sourceRow.modelData.name; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14 }
                            Text { text: sourceRow.modelData.count + " titles"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                        }
                        Item { Layout.fillWidth: true }
                        Text { text: sourceRow.modelData.completion + "% complete"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                    }
                }
            }
        }
    }

    Popup {
        id: genrePicker
        parent: Overlay.overlay
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        width: 360; height: 430
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.sidebar; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 8
            Text { Layout.margins: 16; text: prototype.variant === "brush" ? "Choose a genre brush" : "Assign genre to selection"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.Bold }
            ReviewField { id: assignSearch; Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; placeholderText: "Search genres" }
            ListView {
                id: assignList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: prototype.genres.filter(name => name.toLowerCase().includes(assignSearch.text.toLowerCase()))
                delegate: ReviewButton {
                    required property string modelData
                    width: assignList.width; text: modelData; leftAligned: true
                    onClicked: { prototype.paletteAction("genre", modelData); genrePicker.close() }
                }
            }
        }
    }

    Popup {
        id: folderTagPopup
        parent: Overlay.overlay
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        width: 430; height: 455
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.sidebar; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 10
            Text { Layout.margins: 16; text: "Tag songs in " + prototype.sourceName; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 18; font.weight: Font.Bold }
            Text { Layout.leftMargin: 16; Layout.rightMargin: 16; Layout.fillWidth: true; text: "Choose the main genre for all " + prototype.totalCount + " songs. The folder itself is not tagged."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; wrapMode: Text.WordWrap }
            ListView {
                id: folderGenreList
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: prototype.genres
                delegate: ReviewButton {
                    required property string modelData
                    width: folderGenreList.width; text: modelData; leftAligned: true; selected: root.folderGenre === modelData
                    onClicked: root.folderGenre = modelData
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.margins: 16
                Item { Layout.fillWidth: true }
                ReviewButton { text: "Cancel"; onClicked: folderTagPopup.close() }
                ReviewButton { text: "Tag " + prototype.totalCount + " songs"; primary: true; onClicked: { prototype.tagFolderSongs(root.folderGenre); folderTagPopup.close() } }
            }
        }
    }

    Popup {
        id: tagPicker
        parent: Overlay.overlay
        x: Math.round((root.width - width) / 2); y: Math.round((root.height - height) / 2)
        width: 320; height: 270
        modal: true; focus: true; closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.sidebar; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 8
            Text { Layout.margins: 16; text: "Tags"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 18; font.weight: Font.Bold }
            Text { visible: prototype.tags.length === 0; Layout.leftMargin: 16; text: "No tags yet. Create one below."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            Repeater {
                model: prototype.tags
                ReviewButton { required property string modelData; Layout.fillWidth: true; text: modelData; leftAligned: true; onClicked: { prototype.paletteAction("tag", modelData); tagPicker.close() } }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true; Layout.margins: 16
                ReviewField { id: tagName; Layout.fillWidth: true; placeholderText: "New tag" }
                ReviewButton { text: "Create"; onClicked: { prototype.createTag(tagName.text); tagName.text = "" } }
            }
        }
    }
}
