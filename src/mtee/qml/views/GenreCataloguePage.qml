import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../components"

Rectangle {
    id: page
    required property var manager
    readonly property var state: manager ? manager.state : ({})
    readonly property int padding: width < 700 ? 18 : 32
    property bool creating: false
    property string parentId: ""
    property string parentName: ""
    property string selectedGenreId: ""
    property string query: ""
    property bool showArchived: false
    readonly property var selectedGenre: (state.genres || []).find(
        row => row.genre_id === selectedGenreId
    ) || null

    objectName: "genreCataloguePage"
    color: Theme.editor

    function orderedGenres() {
        const all = (state.genres || []).filter(row => !row.archived || showArchived)
        const result = []
        const search = query.toLowerCase().trim()
        const children = new Map()
        for (const genre of all) {
            const parent = genre.parent_id || ""
            if (!children.has(parent)) children.set(parent, [])
            children.get(parent).push(genre)
        }
        function matches(node) {
            if (node.name.toLowerCase().includes(search)) return true
            return (children.get(node.genre_id) || []).some(matches)
        }
        function append(node, depth, ancestorMatch) {
            const directMatch = ancestorMatch || node.name.toLowerCase().includes(search)
            if (search && !directMatch && !matches(node)) return
            result.push(Object.assign({}, node, { depth: depth,
                hasChildren: (children.get(node.genre_id) || []).length > 0 }))
            for (const child of children.get(node.genre_id) || [])
                append(child, depth + 1, directMatch)
        }
        for (const root of children.get("") || []) append(root, 0, false)
        return result
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 78
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 12
                Text {
                    text: "Genres & tags"
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                    Layout.alignment: Qt.AlignVCenter
                }
                Item { Layout.fillWidth: true }
                TextButton {
                    objectName: "newRootGenreButton"
                    text: "New root genre"
                    kind: "primary"
                    enabledAction: !page.state.busy
                    onClicked: {
                        page.parentId = ""
                        page.parentName = ""
                        page.creating = true
                        genreName.forceActiveFocus()
                    }
                }
            }
        }

        Item {
            visible: page.creating
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 48 : 0
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 8
                Text {
                    text: page.parentId ? "New subgenre in " + page.parentName : "New root genre"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                TextField {
                    id: genreName
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    placeholderText: "Genre name"
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    onAccepted: createButton.clicked()
                    background: Rectangle {
                        color: Theme.surface
                        border.width: 1
                        border.color: genreName.activeFocus ? Theme.focus : Theme.separator
                    }
                }
                TextButton {
                    id: createButton
                    text: "Create"
                    kind: "primary"
                    implicitHeight: 28
                    enabledAction: genreName.text.trim().length > 0 && !page.state.busy
                    onClicked: {
                        page.manager.createGenre(genreName.text, page.parentId)
                        genreName.text = ""
                        page.creating = false
                    }
                }
                TextButton {
                    text: "Cancel"
                    kind: "ghost"
                    implicitHeight: 28
                    onClicked: page.creating = false
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 49
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 12
                TextField {
                    id: genreSearch
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    placeholderText: "Search genres"
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    onTextEdited: page.query = text
                    background: Rectangle {
                        color: Theme.surface
                        border.width: 1
                        border.color: genreSearch.activeFocus ? Theme.focus : Theme.separator
                    }
                }
                Text {
                    text: (page.state.genres || []).length + " genres"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
                TextButton {
                    text: page.showArchived ? "Hide archived" : "Show archived"
                    kind: "ghost"
                    implicitHeight: 28
                    onClicked: page.showArchived = !page.showArchived
                }
            }
        }

        ListView {
            id: genreList
            objectName: "genreTreeList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.orderedGenres()
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}
            delegate: Rectangle {
                id: row
                required property var modelData
                width: genreList.width
                height: 38
                readonly property bool isRoot: modelData.depth === 0
                color: page.selectedGenreId === modelData.genre_id ? Theme.selection
                    : rowMouse.containsMouse ? Theme.surface : "transparent"
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        page.selectedGenreId = row.modelData.genre_id
                        renameField.text = row.modelData.name
                    }
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: page.padding + 22 * row.modelData.depth
                    anchors.rightMargin: page.padding
                    spacing: 9
                    Icon {
                        name: row.modelData.hasChildren ? "chevron-down" : "music"
                        size: 14
                        color: Theme.textSecondary
                        Layout.alignment: Qt.AlignVCenter
                    }
                    Text {
                        Layout.fillWidth: true
                        text: row.modelData.name
                        color: row.modelData.archived ? Theme.textMuted : Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                    IconButton {
                        objectName: "addSubgenreButton"
                        visible: row.isRoot && !row.modelData.archived
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        icon: "plus"
                        iconSize: 16
                        tip: "New subgenre in " + row.modelData.name
                        onClicked: {
                            page.parentId = row.modelData.genre_id
                            page.parentName = row.modelData.name
                            page.creating = true
                            genreName.forceActiveFocus()
                        }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                spacing: 8
                Text {
                    text: page.selectedGenre ? "Selected genre" : "Select a genre to edit"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
                TextField {
                    id: renameField
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    enabled: page.selectedGenre !== null
                    placeholderText: "Genre name"
                    selectByMouse: true
                    color: Theme.textPrimary
                    placeholderTextColor: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    onAccepted: renameButton.clicked()
                    background: Rectangle {
                        color: Theme.surface
                        border.width: 1
                        border.color: renameField.activeFocus ? Theme.focus : Theme.separator
                    }
                }
                TextButton {
                    id: renameButton
                    text: "Rename"
                    kind: "ghost"
                    implicitHeight: 28
                    enabledAction: page.selectedGenre !== null
                        && renameField.text.trim().length > 0 && !page.state.busy
                    onClicked: page.manager.renameGenre(page.selectedGenreId, renameField.text)
                }
                TextButton {
                    text: page.selectedGenre && page.selectedGenre.archived ? "Restore" : "Archive"
                    kind: "ghost"
                    implicitHeight: 28
                    enabledAction: page.selectedGenre !== null && !page.state.busy
                    onClicked: page.manager.setGenreArchived(
                        page.selectedGenreId, !page.selectedGenre.archived
                    )
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 135
            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: page.padding
                anchors.rightMargin: page.padding
                anchors.topMargin: 11
                anchors.bottomMargin: 11
                spacing: 8
                SectionLabel { text: "Tags" }
                Text {
                    Layout.fillWidth: true
                    text: (page.state.tags || []).length
                        ? page.state.tags.map(row => row.name).join(" · ") : "No tags yet"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    elide: Text.ElideRight
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    TextField {
                        id: tagName
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        placeholderText: "Tag name"
                        selectByMouse: true
                        color: Theme.textPrimary
                        placeholderTextColor: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        onAccepted: createTag.clicked()
                        background: Rectangle {
                            color: Theme.surface
                            border.width: 1
                            border.color: tagName.activeFocus ? Theme.focus : Theme.separator
                        }
                    }
                    TextButton {
                        id: createTag
                        text: "Create tag"
                        kind: "neutral"
                        implicitHeight: 28
                        enabledAction: tagName.text.trim().length > 0 && !page.state.busy
                        onClicked: {
                            page.manager.createTag(tagName.text)
                            tagName.text = ""
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            Text {
                anchors.left: parent.left
                anchors.leftMargin: page.padding
                anchors.verticalCenter: parent.verticalCenter
                text: page.state.error || page.state.message
                color: page.state.error ? Theme.danger : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                elide: Text.ElideRight
            }
        }
    }
}
