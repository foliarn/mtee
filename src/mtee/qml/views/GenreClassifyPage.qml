import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../components"

Rectangle {
    id: page
    required property var workspace
    required property var manager
    property int bottomInset: 0
    readonly property var state: manager ? manager.state : ({})
    readonly property int padding: width < 700 ? 18 : 32
    readonly property bool showArtist: width >= 700
    readonly property bool showTags: width >= 900
    readonly property bool showReview: width >= 620
    signal sourceRequested()
    signal genreRequested(string mode)
    signal tagRequested()
    signal folderGenreRequested()
    signal trackGenresRequested(string trackId, var genres)

    objectName: "genreClassifyPage"
    color: Theme.editor

    function genreName(identity) {
        for (const row of state.genres || [])
            if (row.genre_id === identity)
                return row.name
        return "—"
    }

    function tagNames(ids) {
        const names = []
        for (const identity of ids || []) {
            for (const row of state.tags || []) {
                if (row.tag_id === identity) {
                    names.push(row.name)
                    break
                }
            }
        }
        return names.join(", ")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 148

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                anchors.topMargin: 17
                anchors.bottomMargin: 12
                spacing: 8

                SectionLabel {
                    text: page.state.sourceKind === "playlist" ? "PLAYLIST" : "FOLDER"
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    Item {
                        id: sourceControl
                        objectName: "genreSourceButton"
                        Layout.preferredWidth: Math.min(400,
                            Math.max(150, sourceTitle.implicitWidth + 64))
                        Layout.preferredHeight: 38
                        Rectangle {
                            anchors.fill: parent
                            color: sourceMouse.containsMouse ? Theme.surface : "transparent"
                        }
                        RowLayout {
                            anchors.fill: parent
                            spacing: 8
                            Text {
                                id: sourceTitle
                                Layout.fillWidth: true
                                text: page.state.sourceLabel || "Choose source"
                                color: Theme.textPrimary
                                font.family: Theme.displayFontFamily
                                font.pixelSize: page.width < 700 ? 23 : 28
                                font.weight: Font.Bold
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                            }
                            Icon {
                                name: "chevron-down"
                                size: 17
                                color: Theme.textSecondary
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                        MouseArea {
                            id: sourceMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.sourceRequested()
                        }
                    }

                    Text {
                        text: page.state.total + " titles · " + page.state.reviewed + " reviewed"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        verticalAlignment: Text.AlignVCenter
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Item { Layout.fillWidth: true }
                    TextField {
                        id: search
                        objectName: "genreSourceSearch"
                        Layout.preferredWidth: Math.min(230, page.width * 0.25)
                        Layout.preferredHeight: 28
                        placeholderText: "Search this source"
                        text: page.state.search || ""
                        selectByMouse: true
                        color: Theme.textPrimary
                        placeholderTextColor: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        onTextEdited: page.manager.setSearch(text)
                        background: Rectangle {
                            color: Theme.surface
                            border.width: 1
                            border.color: search.activeFocus ? Theme.focus : Theme.separator
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    TextButton {
                        visible: page.state.sourceKind === "folder"
                        text: "Tag folder songs…"
                        kind: "ghost"
                        implicitHeight: 28
                        onClicked: page.folderGenreRequested()
                    }
                    TextButton {
                        text: page.state.interactionMode === "brush" ? "Brush: "
                            + page.genreName(page.state.brushId) : "Assign genre…"
                        kind: "ghost"
                        implicitHeight: 28
                        onClicked: page.genreRequested(page.state.interactionMode === "brush"
                            ? "brush" : "selection")
                    }
                    TextButton {
                        text: "Tag…"
                        kind: "ghost"
                        implicitHeight: 28
                        onClicked: page.tagRequested()
                    }
                    TextButton {
                        text: page.state.interactionMode === "brush" ? "Selection" : "Brush"
                        kind: "ghost"
                        implicitHeight: 28
                        onClicked: page.manager.setInteractionMode(
                            page.state.interactionMode === "brush" ? "selection" : "brush"
                        )
                    }
                    Item { Layout.fillWidth: true }
                    TextButton {
                        text: "All tracks"
                        kind: page.state.viewMode === "all" ? "neutral" : "ghost"
                        implicitHeight: 28
                        onClicked: page.manager.setViewMode("all")
                    }
                    TextButton {
                        text: "To review"
                        kind: page.state.viewMode === "to_review" ? "neutral" : "ghost"
                        implicitHeight: 28
                        onClicked: page.manager.setViewMode("to_review")
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 8
                Text {
                    text: (page.state.selectedIds || []).length + " selected"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    Layout.alignment: Qt.AlignVCenter
                }
                TextButton {
                    text: "Mark " + (page.state.selectedIds || []).length + " as reviewed"
                    kind: (page.state.selectedIds || []).length ? "primary" : "neutral"
                    enabledAction: (page.state.selectedIds || []).length > 0 && !page.state.busy
                    implicitHeight: 28
                    onClicked: page.manager.markSelectedReviewed()
                }
                Item { Layout.fillWidth: true }
                TextButton {
                    text: "Organize files"
                    kind: "ghost"
                    implicitHeight: 28
                    enabledAction: page.state.total > 0
                    onClicked: page.workspace.openGenreManagerView("organize", "Organize")
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 10
                Text { text: "#"; Layout.preferredWidth: 30; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Item { Layout.preferredWidth: 40 }
                Text { text: "Title"; Layout.fillWidth: true; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { visible: page.showArtist; text: "Artist"; Layout.preferredWidth: 150; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { text: "Main genre"; Layout.preferredWidth: 120; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { visible: page.showTags; text: "Tags"; Layout.preferredWidth: 100; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { visible: page.showReview; text: "Reviewed"; Layout.preferredWidth: 66; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Item { Layout.preferredWidth: page.state.interactionMode === "brush" ? 72 : 34 }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

        ListView {
            id: list
            objectName: "genreTrackList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.manager ? page.manager.rowsModel : null
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}

            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                width: list.width
                height: Theme.rowHeight
                readonly property bool selected: (page.state.selectedIds || []).indexOf(modelData.id) >= 0
                color: selected ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: mouse => page.manager.selectTrack(
                        row.modelData.id,
                        Boolean(mouse.modifiers & Qt.ControlModifier),
                        Boolean(mouse.modifiers & Qt.ShiftModifier)
                    )
                    onDoubleClicked: page.workspace.playTrackFromRows(
                        row.modelData.id, "genre_manager:" + page.state.sessionId,
                        page.manager.rowsModel.rows
                    )
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: page.padding
                    anchors.rightMargin: page.padding
                    spacing: 10
                    Text {
                        text: String(row.index + 1)
                        Layout.preferredWidth: 30
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        verticalAlignment: Text.AlignVCenter
                    }
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        color: Theme.surface
                        Image {
                            anchors.fill: parent
                            source: row.modelData.coverUrl || ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.title
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    Text {
                        visible: page.showArtist
                        Layout.preferredWidth: 150
                        text: row.modelData.artist
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    Text {
                        id: mainGenre
                        Layout.preferredWidth: 120
                        text: row.modelData.genres.length
                            ? page.genreName(row.modelData.genres[0])
                            + (row.modelData.genres.length > 1 ? " +" + (row.modelData.genres.length - 1) : "")
                            : "—"
                        color: row.modelData.genres.length ? Theme.textPrimary : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.trackGenresRequested(
                                row.modelData.id, row.modelData.genres
                            )
                        }
                    }
                    Text {
                        visible: page.showTags
                        Layout.preferredWidth: 100
                        text: page.tagNames(row.modelData.tags) || "—"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    Text {
                        visible: page.showReview
                        Layout.preferredWidth: 66
                        text: row.modelData.reviewed ? "✓" : "—"
                        color: row.modelData.reviewed ? Theme.primary : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    IconButton {
                        visible: page.state.interactionMode === "brush"
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        icon: "plus"
                        iconSize: 16
                        tip: "Apply or remove brush"
                        onClicked: {
                            const identity = page.state.brushId
                            const current = page.state.brushKind === "tag"
                                ? row.modelData.tags : row.modelData.genres
                            page.manager.paint(row.modelData.id, identity, current.indexOf(identity) < 0)
                        }
                    }
                    IconButton {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        icon: "play"
                        iconSize: 17
                        tip: "Play"
                        onClicked: page.workspace.playTrackFromRows(
                            row.modelData.id, "genre_manager:" + page.state.sessionId,
                            page.manager.rowsModel.rows
                        )
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 12
                Text {
                    Layout.fillWidth: true
                    text: page.state.error || page.state.message
                        || (page.state.busy ? "Loading…" : "")
                    color: page.state.error ? Theme.danger : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
                TextButton {
                    text: "Undo"
                    kind: "ghost"
                    implicitHeight: 28
                    enabledAction: page.state.canUndo && !page.state.busy
                    onClicked: page.manager.undo()
                }
            }
        }
    }
}
