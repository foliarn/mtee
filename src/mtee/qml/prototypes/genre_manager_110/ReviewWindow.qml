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
                : action.hovered ? "#303036" : Theme.surface
            border.width: action.activeFocus ? 1 : 0
            border.color: Theme.focus
            radius: Theme.radius
        }
        contentItem: Text {
            id: label
            text: action.text
            color: action.primary ? Theme.textOnColor : action.danger ? Theme.danger : Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: action.primary ? Font.Bold : Font.Medium
            leftPadding: action.leftAligned ? 14 : 0
            horizontalAlignment: action.leftAligned ? Text.AlignLeft : Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component ReviewField: TextField {
        color: Theme.textPrimary
        placeholderTextColor: Theme.textSecondary
        selectByMouse: true
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
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
            Layout.preferredHeight: 38
            color: Theme.chrome
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 16
                Text {
                    text: "M"
                    color: Theme.primary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: 21
                    font.weight: Font.ExtraBold
                }
                Text {
                    text: "MTEE"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    font.weight: Font.Bold
                }
                Rectangle { width: 1; height: 18; color: Theme.separator }
                Text {
                    text: "Genre Manager review"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "Prototype · synthetic data"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
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
                    spacing: 4
                    topPadding: 12
                    ReviewButton {
                        width: 48
                        text: "E"
                        ToolTip.visible: hovered
                        ToolTip.text: "Explorer (simulated)"
                        onClicked: prototype.setSection("Plugins")
                    }
                    ReviewButton {
                        width: 48
                        text: "P"
                        selected: true
                        ToolTip.visible: hovered
                        ToolTip.text: "Plugins"
                        onClicked: prototype.setSection("Plugins")
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 222
                Layout.fillHeight: true
                color: Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10
                    Text {
                        text: "Plugins"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: Font.Bold
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "← All plugins"
                        onClicked: prototype.setSection("Plugins")
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Text {
                        text: "Genre Manager"
                        color: Theme.textPrimary
                        font.family: Theme.displayFontFamily
                        font.pixelSize: 19
                        font.weight: Font.Bold
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Classify"
                        selected: prototype.section === "Classify"
                        onClicked: prototype.setSection("Classify")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Genres & tags"
                        selected: prototype.section === "Genres"
                        onClicked: prototype.setSection("Genres")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Uncertain"
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
                        selected: prototype.variant === "selection"
                        onClicked: prototype.setVariant("selection")
                    }
                    ReviewButton {
                        Layout.fillWidth: true
                        text: "Brush"
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

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 65
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 24
                            anchors.rightMargin: 24
                            Text {
                                text: prototype.section === "Plugins" ? "Plugins"
                                    : prototype.section === "Organize" ? "Organize files"
                                    : prototype.section === "Genres" ? "Genres & tags"
                                    : prototype.section === "Uncertain" ? "Uncertain"
                                    : "Classify"
                                color: Theme.textPrimary
                                font.family: Theme.displayFontFamily
                                font.pixelSize: 26
                                font.weight: Font.Bold
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: prototype.variant === "brush" ? "Brush variant" : "Selection variant"
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

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
            Layout.preferredHeight: 55
            color: Theme.chrome
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                spacing: 16
                Text {
                    text: prototype.playingTitle || "No track playing"
                    color: prototype.playingTitle ? Theme.primary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                    font.weight: Font.Medium
                }
                ReviewButton {
                    text: "Play / pause"
                    onClicked: prototype.togglePause()
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: prototype.playerError ? "Native player unavailable" : "Native player ready"
                    color: prototype.playerError ? Theme.warning : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }
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
        RowLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 121
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: "Source"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                        }
                        ReviewButton { text: "House folder"; selected: prototype.scenario === "house"; onClicked: prototype.setScenario("house") }
                        ReviewButton { text: "Playlist"; selected: prototype.scenario === "playlist"; onClicked: prototype.setScenario("playlist") }
                        ReviewButton { text: "80 of 100"; selected: prototype.scenario === "batch"; onClicked: prototype.setScenario("batch") }
                        ReviewButton { text: "New tracks"; selected: prototype.scenario === "new"; onClicked: prototype.setScenario("new") }
                        Item { Layout.fillWidth: true }
                        ReviewButton {
                            text: "Include subfolders"
                            selected: prototype.includeSubfolders
                            onClicked: prototype.toggleSubfolders()
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: prototype.reviewedCount + " / " + prototype.totalCount + " reviewed"
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: 13
                        }
                        ReviewField {
                            Layout.preferredWidth: 180
                            placeholderText: "Search this source"
                            onTextChanged: prototype.setSearch(text)
                        }
                        Item { Layout.fillWidth: true }
                        ReviewButton { text: "All tracks"; selected: prototype.view === "All tracks"; onClicked: prototype.setView("All tracks") }
                        ReviewButton { text: "To review"; selected: prototype.view === "To review"; onClicked: prototype.setView("To review") }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: prototype.selectedCount + " selected"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                        }
                        ReviewButton {
                            text: "Mark " + prototype.selectedCount + " as reviewed"
                            primary: prototype.selectedCount > 0
                            onClicked: prototype.markReviewed()
                        }
                        ReviewButton { text: "Simulate save error"; onClicked: prototype.failNext() }
                        Item { Layout.fillWidth: true }
                        ReviewButton { text: "Organize files"; onClicked: prototype.preparePreview() }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Text { text: "Track"; Layout.fillWidth: true; color: Theme.textSecondary; font.pixelSize: 12; font.family: Theme.fontFamily }
                    Text { text: "Classification"; Layout.preferredWidth: 255; color: Theme.textSecondary; font.pixelSize: 12; font.family: Theme.fontFamily }
                    Text { text: "Review"; Layout.preferredWidth: 58; color: Theme.textSecondary; font.pixelSize: 12; font.family: Theme.fontFamily }
                }
                ListView {
                    id: trackList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: prototype.tracks
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Rectangle {
                        id: trackRow
                        required property var modelData
                        required property int index
                        width: trackList.width
                        height: 62
                        color: modelData.selected ? Theme.selection : index % 2 ? Theme.editor : "#1C1C20"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: (mouse) => prototype.selectTrack(trackRow.modelData.id, mouse.modifiers)
                        }
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 20
                            anchors.rightMargin: 20
                            spacing: 9
                            ReviewButton {
                                text: "Play"
                                implicitWidth: 52
                                ToolTip.visible: hovered
                                ToolTip.text: "Play this track"
                                onClicked: prototype.playTrack(trackRow.modelData.id)
                            }
                            ReviewButton {
                                visible: prototype.variant === "brush"
                                text: "Mark"
                                implicitWidth: 54
                                ToolTip.visible: hovered
                                ToolTip.text: "Apply " + prototype.brushLabel
                                onClicked: prototype.paintTrack(trackRow.modelData.id)
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Text {
                                    text: trackRow.modelData.title
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 13
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: trackRow.modelData.artist + "  ·  " + trackRow.modelData.source
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            ColumnLayout {
                                Layout.preferredWidth: 255
                                spacing: 2
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Text {
                                        text: trackRow.modelData.genres.length ? trackRow.modelData.genres.join("  ›  ") : "No genre"
                                        color: trackRow.modelData.genres.length ? Theme.textPrimary : Theme.textSecondary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    ReviewButton {
                                        visible: trackRow.modelData.genres.length > 1
                                        text: "Promote 2nd"
                                        implicitWidth: 92
                                        implicitHeight: 25
                                        ToolTip.visible: hovered
                                        ToolTip.text: "Make " + (trackRow.modelData.genres[1] || "") + " primary"
                                        onClicked: prototype.makePrimary(trackRow.modelData.id, trackRow.modelData.genres[1])
                                    }
                                }
                                Text {
                                    text: trackRow.modelData.tags.length ? trackRow.modelData.tags.join(" · ") : "No tags"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 11
                                    Layout.fillWidth: true
                                }
                            }
                            ReviewButton {
                                text: trackRow.modelData.reviewed ? "Yes" : "No"
                                implicitWidth: 58
                                selected: trackRow.modelData.reviewed
                                ToolTip.visible: hovered
                                ToolTip.text: trackRow.modelData.reviewed ? "Reviewed" : "To review"
                                onClicked: prototype.selectTrack(trackRow.modelData.id, 0)
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: root.width < 1100 ? 185 : 235
                Layout.fillHeight: true
                color: Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8
                    Text {
                        text: prototype.variant === "brush" ? "Choose a brush" : "Assign to selection"
                        color: Theme.textPrimary
                        font.family: Theme.displayFontFamily
                        font.pixelSize: 17
                        font.weight: Font.Bold
                    }
                    Text {
                        Layout.fillWidth: true
                        text: prototype.variant === "brush" ? "Click a marker to add or remove. Selection stays separate." : "Ctrl or Shift click tracks, then choose a genre or tag."
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    Text { text: "Genres"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    Repeater {
                        model: prototype.genres
                        ReviewButton {
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            selected: prototype.variant === "brush" && prototype.brushLabel === "genre: " + modelData
                            onClicked: prototype.paletteAction("genre", modelData)
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Text { text: "Tags"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                    Text {
                        visible: prototype.tags.length === 0
                        Layout.fillWidth: true
                        text: "No tags yet. Create one below."
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                    Repeater {
                        model: prototype.tags
                        ReviewButton {
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            selected: prototype.variant === "brush" && prototype.brushLabel === "tag: " + modelData
                            onClicked: prototype.paletteAction("tag", modelData)
                        }
                    }
                    ReviewField { id: tagInput; Layout.fillWidth: true; placeholderText: "New tag name"; onAccepted: { prototype.createTag(text); text = "" } }
                    ReviewButton { Layout.fillWidth: true; text: "Create tag"; onClicked: { prototype.createTag(tagInput.text); tagInput.text = "" } }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    ReviewButton { Layout.fillWidth: true; text: "Remove Deep House"; onClicked: prototype.removeFromSelection("genre", "Deep House") }
                    ReviewButton { Layout.fillWidth: true; text: "Make Deep House primary"; onClicked: if (prototype.tracks.length) prototype.makePrimary(prototype.tracks[0].id, "Deep House") }
                    Item { Layout.fillHeight: true }
                    Text {
                        Layout.fillWidth: true
                        text: prototype.variant === "brush" ? "Active: " + prototype.brushLabel : prototype.selectedCount + " target tracks"
                        wrapMode: Text.WordWrap
                        color: Theme.primary
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    Component {
        id: genresPage
        ColumnLayout {
            anchors.margins: 24
            spacing: 12
            Text {
                text: "Local catalogue"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 19
                font.weight: Font.Bold
            }
            Text {
                text: "House is a family. Its subgenres use full names; other families keep their own names."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 13
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Repeater {
                    model: prototype.genres
                    ReviewButton {
                        required property string modelData
                        Layout.preferredWidth: 340
                        text: modelData.endsWith("House") && modelData !== "House" ? "    " + modelData : modelData
                        leftAligned: true
                        selected: catalogueSelection.text === modelData
                        onClicked: catalogueSelection.text = modelData
                    }
                }
            }
            RowLayout {
                ReviewField { id: newGenre; Layout.preferredWidth: 210; placeholderText: "New genre" }
                ReviewButton { text: "Create under House"; onClicked: { prototype.createGenre(newGenre.text, "House"); newGenre.text = "" } }
                ReviewButton { text: "Create root"; onClicked: { prototype.createGenre(newGenre.text, ""); newGenre.text = "" } }
            }
            RowLayout {
                ReviewField { id: catalogueSelection; Layout.preferredWidth: 160; text: "Deep House"; readOnly: true }
                ReviewField { id: renamedGenre; Layout.preferredWidth: 180; placeholderText: "New name" }
                ReviewButton { text: "Rename"; onClicked: { prototype.renameGenre(catalogueSelection.text, renamedGenre.text); catalogueSelection.text = renamedGenre.text; renamedGenre.text = "" } }
                ReviewButton { text: "Archive"; onClicked: prototype.archiveGenre(catalogueSelection.text) }
            }
            RowLayout {
                visible: prototype.archivedGenres.length > 0
                Text { text: "Archived: " + prototype.archivedGenres.join(", "); color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
                ReviewButton { text: "Restore first"; onClicked: if (prototype.archivedGenres.length) prototype.restoreGenre(prototype.archivedGenres[0]) }
            }
            Text { text: "Tags are separate and start empty"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 15 }
            RowLayout {
                ReviewField { id: catalogueTag; Layout.preferredWidth: 220; placeholderText: "e.g. banger"; onAccepted: { prototype.createTag(text); text = "" } }
                ReviewButton { text: "Create tag"; primary: true; onClicked: { prototype.createTag(catalogueTag.text); catalogueTag.text = "" } }
                Text { text: prototype.tags.length ? prototype.tags.join(" · ") : "No tags created"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12 }
            }
            Text {
                text: "Reparenting and deletion rules are proposals to settle during the review."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 12
            }
            Item { Layout.fillHeight: true }
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
            anchors.margins: 24
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: prototype.preview.length + " reviewed tracks in this preview"
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: 19
                    font.weight: Font.Bold
                }
                Item { Layout.fillWidth: true }
                ReviewButton { text: "Back to classify"; onClicked: prototype.setSection("Classify") }
            }
            Text {
                text: "Preview only. Sources, folders and destinations below are illustrative; no folder is created and no file is moved."
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: prototype.preview
                delegate: Rectangle {
                    id: previewRow
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: 52
                    color: index % 2 ? Theme.editor : Theme.surface
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        Text { text: previewRow.modelData.title; Layout.fillWidth: true; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13; elide: Text.ElideRight }
                        Text { text: previewRow.modelData["from"] + "  →  " + previewRow.modelData.to; Layout.preferredWidth: 300; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 12; elide: Text.ElideRight }
                    }
                }
            }
            ReviewButton { text: "Move files (unavailable in prototype)"; enabled: false }
        }
    }
}
