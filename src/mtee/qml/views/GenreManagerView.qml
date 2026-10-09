import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../components"

Rectangle {
    id: page
    required property var workspace
    required property var tab
    property int bottomInset: 0
    readonly property var manager: workspace.genreManager
    readonly property var state: manager ? manager.state : ({})
    readonly property string pageKind: tab ? String(tab.id).split(":")[1] : "classify"
    property string pickerMode: "selection"
    property string folderGenreId: ""
    property bool folderTab: true
    property bool includeSubfolders: false
    property string activeTrackId: ""
    property var activeTrackGenres: []

    objectName: "genreManagerView"
    color: Theme.editor

    function genreName(identity) {
        for (const row of state.genres || [])
            if (row.genre_id === identity)
                return row.name
        return "Genre"
    }

    Loader {
        anchors.fill: parent
        sourceComponent: page.pageKind === "genres" ? cataloguePage
            : page.pageKind === "uncertain" ? uncertainPage
            : page.pageKind === "organize" ? organizePage
            : classifyPage
    }

    Component {
        id: classifyPage
        GenreClassifyPage {
            workspace: page.workspace
            manager: page.manager
            bottomInset: page.bottomInset
            onSourceRequested: sourcePicker.open()
            onGenreRequested: mode => {
                page.pickerMode = mode
                genrePicker.open()
            }
            onTagRequested: tagPicker.open()
            onFolderGenreRequested: {
                page.pickerMode = "folder"
                genrePicker.open()
            }
            onTrackGenresRequested: (trackId, genres) => {
                page.activeTrackId = trackId
                page.activeTrackGenres = genres
                trackGenres.open()
            }
        }
    }

    Component {
        id: cataloguePage
        GenreCataloguePage { manager: page.manager }
    }

    Component {
        id: uncertainPage
        GenreUncertainPage { manager: page.manager }
    }

    Component {
        id: organizePage
        GenreOrganizePage { manager: page.manager; workspace: page.workspace }
    }

    Popup {
        id: sourcePicker
        objectName: "genreSourcePicker"
        x: Math.round((page.width - width) / 2)
        y: Math.round((page.height - height) / 2)
        width: Math.min(700, page.width - 48)
        height: Math.min(600, page.height - 48)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 0
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 62
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 14
                    Text { text: "Choose source"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 20; font.weight: Font.Bold }
                    Item { Layout.fillWidth: true }
                    IconButton { icon: "close"; iconSize: 16; tip: "Close"; onClicked: sourcePicker.close() }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.bottomMargin: 12
                spacing: 6
                TextButton { text: "Folders"; kind: page.folderTab ? "neutral" : "ghost"; onClicked: page.folderTab = true }
                TextButton { text: "Playlists"; kind: !page.folderTab ? "neutral" : "ghost"; onClicked: page.folderTab = false }
                Item { Layout.fillWidth: true }
                TextButton {
                    visible: page.folderTab
                    text: page.includeSubfolders ? "Include subfolders ✓" : "Include subfolders"
                    kind: "ghost"
                    onClicked: page.includeSubfolders = !page.includeSubfolders
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: sourceList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: (page.state.sources || []).filter(
                    item => item.kind === (page.folderTab ? "folder" : "playlist")
                )
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}
                delegate: Rectangle {
                    id: sourceRow
                    required property var modelData
                    width: sourceList.width
                    height: 46
                    color: sourceMouse.containsMouse ? Theme.surface : "transparent"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 12
                        Icon { name: page.folderTab ? "folder" : "playlists"; size: 16; color: Theme.textSecondary }
                        Text { Layout.fillWidth: true; text: sourceRow.modelData.name; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary; elide: Text.ElideRight }
                        Text { text: sourceRow.modelData.count + " tracks"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        Text { Layout.preferredWidth: 44; text: sourceRow.modelData.completion + "%"; color: Theme.primary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary; horizontalAlignment: Text.AlignRight }
                    }
                    MouseArea {
                        id: sourceMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            page.manager.openSource(
                                sourceRow.modelData.kind, sourceRow.modelData.key,
                                sourceRow.modelData.rootId,
                                page.folderTab && page.includeSubfolders
                            )
                            sourcePicker.close()
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: genrePicker
        x: Math.round((page.width - width) / 2)
        y: Math.round((page.height - height) / 2)
        width: Math.min(500, page.width - 48)
        height: Math.min(560, page.height - 48)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 0
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: page.pickerMode === "folder" ? "Tag folder songs as…"
                        : page.pickerMode === "brush" ? "Choose brush genre" : "Assign genre"
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: 19
                    font.weight: Font.Bold
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: genreOptions
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: (page.state.genres || []).filter(row => !row.archived)
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}
                delegate: Rectangle {
                    id: option
                    required property var modelData
                    width: genreOptions.width
                    height: 38
                    color: optionMouse.containsMouse ? Theme.surface : "transparent"
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: option.modelData.parent_id ? 36 : 20
                        anchors.verticalCenter: parent.verticalCenter
                        text: option.modelData.name
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                    MouseArea {
                        id: optionMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            const identity = option.modelData.genre_id
                            genrePicker.close()
                            if (page.pickerMode === "folder") {
                                page.folderGenreId = identity
                                folderConfirm.open()
                            } else if (page.pickerMode === "brush") {
                                page.manager.setBrush("genre", identity)
                            } else {
                                page.manager.addGenreToSelection(identity)
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: tagPicker
        x: Math.round((page.width - width) / 2)
        y: Math.round((page.height - height) / 2)
        width: Math.min(430, page.width - 48)
        height: Math.min(440, page.height - 48)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 0
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.topMargin: 16
                Layout.bottomMargin: 16
                text: page.state.interactionMode === "brush" ? "Choose tag brush" : "Assign tag"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 19
                font.weight: Font.Bold
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            ListView {
                id: tagOptions
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: (page.state.tags || []).filter(row => !row.archived)
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ThinScrollBar {}
                delegate: Rectangle {
                    id: tagOption
                    required property var modelData
                    width: tagOptions.width
                    height: 38
                    color: tagMouse.containsMouse ? Theme.surface : "transparent"
                    Text { anchors.left: parent.left; anchors.leftMargin: 20; anchors.right: removeTag.left; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: tagOption.modelData.name; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary; elide: Text.ElideRight }
                    MouseArea {
                        id: tagMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            tagPicker.close()
                            if (page.state.interactionMode === "brush")
                                page.manager.setBrush("tag", tagOption.modelData.tag_id)
                            else
                                page.manager.addTagToSelection(tagOption.modelData.tag_id)
                        }
                    }
                    TextButton {
                        id: removeTag
                        visible: page.state.interactionMode !== "brush"
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Remove"
                        kind: "ghost"
                        implicitHeight: 26
                        enabledAction: (page.state.selectedIds || []).length > 0
                        onClicked: {
                            page.manager.removeTagFromSelection(tagOption.modelData.tag_id)
                            tagPicker.close()
                        }
                    }
                }
            }
            Text {
                visible: !(page.state.tags || []).length
                Layout.leftMargin: 20
                Layout.bottomMargin: 14
                text: "No tags yet. Create one in Genres & tags."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    Popup {
        id: trackGenres
        x: Math.round((page.width - width) / 2)
        y: Math.round((page.height - height) / 2)
        width: Math.min(540, page.width - 48)
        height: Math.min(360, 72 + page.activeTrackGenres.length * 52)
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
        contentItem: ColumnLayout {
            spacing: 0
            Text {
                Layout.leftMargin: 20
                Layout.topMargin: 18
                Layout.bottomMargin: 14
                text: "Track genres"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 19
                font.weight: Font.Bold
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
            Text {
                visible: !page.activeTrackGenres.length
                Layout.leftMargin: 20
                Layout.topMargin: 18
                text: "No genre assigned yet"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Repeater {
                model: page.activeTrackGenres
                delegate: RowLayout {
                    required property string modelData
                    required property int index
                    Layout.fillWidth: true
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.preferredHeight: 50
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: page.genreName(modelData) + (index === 0 ? " · Main" : "")
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                    TextButton {
                        visible: index > 0
                        text: "Make primary"
                        kind: "ghost"
                        implicitHeight: 27
                        onClicked: {
                            page.manager.makePrimary(page.activeTrackId, modelData)
                            trackGenres.close()
                        }
                    }
                    IconButton {
                        visible: index > 0
                        width: 27
                        height: 27
                        icon: "arrow-up"
                        iconSize: 15
                        tip: "Move up"
                        onClicked: {
                            page.manager.moveGenre(page.activeTrackId, modelData, -1)
                            trackGenres.close()
                        }
                    }
                    TextButton {
                        text: "Remove"
                        kind: "ghost"
                        implicitHeight: 27
                        onClicked: {
                            page.manager.removeGenreFromTrack(page.activeTrackId, modelData)
                            trackGenres.close()
                        }
                    }
                }
            }
            Item { Layout.fillHeight: true }
        }
    }

    Popup {
        id: folderConfirm
        x: Math.round((page.width - width) / 2)
        y: Math.round((page.height - height) / 2)
        width: Math.min(520, page.width - 48)
        height: 190
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: Theme.sidebar; border.width: 1; border.color: Theme.separator }
        contentItem: ColumnLayout {
            anchors.margins: 20
            spacing: 12
            Text { text: "Tag folder songs"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 20; font.weight: Font.Bold }
            Text {
                Layout.fillWidth: true
                text: "Apply " + page.genreName(page.folderGenreId) + " to " + page.state.total
                    + " songs in " + page.state.sourceLabel + "? The folder itself is not tagged."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                TextButton { text: "Cancel"; kind: "ghost"; onClicked: folderConfirm.close() }
                TextButton {
                    text: "Apply to songs"
                    kind: "primary"
                    onClicked: {
                        page.manager.assignGenreToSource(page.folderGenreId)
                        folderConfirm.close()
                    }
                }
            }
        }
    }
}
