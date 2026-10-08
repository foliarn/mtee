import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee

Popup {
    id: manager
    objectName: "genreManager"
    required property var model
    property bool advancedAllowed: false
    property string section: "genre"
    property var selected: null
    property var members: []
    property var parentChoices: [{genre_id:"", path:"Root family"}].concat(Array.from(model.catalog.genres || []))
    width: Math.min(980, parent ? parent.width - 32 : 980)
    height: Math.min(700, parent ? parent.height - 32 : 700)
    modal: true
    focus: true
    anchors.centerIn: parent
    padding: 20
    background: Rectangle { color: Theme.editor; border.color: Theme.separator; radius: 8 }
    function identity(node) { return section === "genre" ? node.genre_id : section === "meta" ? node.meta_id : node.tag_id }
    function choose(node) {
        selected = node
        nameInput.text = node.name
        aliasesInput.text = node.aliases ? Array.from(node.aliases).join(", ") : ""
        positionInput.text = String(node.position || 0)
        colorInput.text = node.color || ""
        parentInput.currentIndex = parentChoices.findIndex(p => p.genre_id === (node.parent_id || ""))
        members = Array.from(node.members || [])
    }
    function save() {
        let values = {name: nameInput.text}
        if (section === "genre") {
            values.parent_id = parentChoices[parentInput.currentIndex].genre_id
            values.position = Number(positionInput.text)
            values.aliases = aliasesInput.text.split(",").map(s => s.trim()).filter(s => s.length)
        } else if (section === "meta") values.members = members
        else values.color = colorInput.text
        model.edit(section, selected ? "edit" : "create", selected ? identity(selected) : "", values, selected ? selected.revision : 0)
    }
    Connections {
        target: manager.model
        function onChanged() {
            if (!manager.selected || manager.model.busy) return
            const rows = manager.section === "genre" ? manager.model.catalog.genres : manager.section === "meta" ? manager.model.catalog.metas : manager.model.catalog.tags
            const next = Array.from(rows).find(n => manager.identity(n) === manager.identity(manager.selected))
            manager.selected = next || null
        }
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Text { text: "Genre manager"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 24; Layout.fillWidth: true }
            TextButton { text: "Retry"; visible: manager.model.message.indexOf("Could not save") === 0; enabled: !manager.model.busy; onClicked: manager.model.retry() }
            TextButton { text: "Reload"; enabled: !manager.model.busy; onClicked: manager.model.reload() }
            TextButton { text: "Undo"; enabled: manager.model.canUndo; onClicked: manager.model.undo() }
            TextButton { text: "Close"; onClicked: manager.close() }
        }
        RowLayout {
            Repeater {
                model: [{kind:"genre",label:"Genres"},{kind:"meta",label:"Meta-families"},{kind:"tag",label:"Local tags"}]
                TextButton {
                    required property var modelData
                    text: modelData.label
                    kind: manager.section === modelData.kind ? "neutral" : "ghost"
                    onClicked: { manager.section = modelData.kind; manager.selected = null; nameInput.text = "" }
                }
            }
            Item { Layout.fillWidth: true }
            GenreCheckBox { id: showArchived; text: "Show archived" }
        }
        GenreTextField {
            id: search
            objectName: "genreManagerSearch"
            Layout.fillWidth: true
            placeholderText: "Search names, paths or aliases"
            color: Theme.textPrimary
            background: Rectangle { color: Theme.surface; border.color: Theme.separator }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            ListView {
                id: catalogList
                objectName: "genreManagerTable"
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.minimumWidth: 220; Layout.preferredWidth: 560
                clip: true
                model: {
                    const source = manager.section === "genre" ? manager.model.catalog.genres : manager.section === "meta" ? manager.model.catalog.metas : manager.model.catalog.tags
                    return Array.from(source || []).filter(n => (showArchived.checked || !n.archived) && ((n.path || n.name) + " " + Array.from(n.aliases || []).join(" ")).toLowerCase().includes(search.text.toLowerCase()))
                }
                ScrollBar.vertical: ThinScrollBar {}
                delegate: Rectangle {
                    id: catalogRow
                    objectName: "genreCatalogRow_" + (modelData.genre_id || modelData.meta_id || modelData.tag_id)
                    required property var modelData
                    width: ListView.view.width; height: 42
                    property string genreId: modelData.genre_id || ""
                    property int genreRevision: modelData.revision
                    color: manager.selected && manager.identity(manager.selected) === manager.identity(modelData) ? Theme.selection : Theme.surface
                    opacity: modelData.archived ? 0.55 : 1
                    Text {
                        x: 10; anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 64
                        text: (catalogRow.modelData.path || catalogRow.modelData.name)
                        color: Theme.textPrimary; font.family: Theme.fontFamily; elide: Text.ElideRight
                    }
                    Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: catalogRow.modelData.count === undefined ? "" : catalogRow.modelData.count; color: Theme.textSecondary }
                    TapHandler { onTapped: manager.choose(catalogRow.modelData) }
                    Drag.source: catalogRow
                    Drag.keys: ["mtee-genre"]
                    Drag.supportedActions: Qt.MoveAction
                    Drag.hotSpot.x: rowDrag.centroid.position.x
                    Drag.hotSpot.y: rowDrag.centroid.position.y
                    DragHandler {
                        id: rowDrag
                        target: null
                        enabled: manager.section === "genre" && !manager.model.busy
                        onActiveChanged: { if (active) catalogRow.Drag.active = true; else { catalogRow.Drag.drop(); catalogRow.Drag.active = false } }
                    }
                    DropArea {
                        anchors.fill: parent
                        keys: ["mtee-genre"]
                        enabled: manager.section === "genre"
                        onDropped: drop => {
                            if (drop.source && drop.source.genreId !== catalogRow.genreId) {
                                const above = drop.y < height / 3
                                manager.model.edit("genre", "edit", drop.source.genreId, {parent_id: above ? (catalogRow.modelData.parent_id || "") : catalogRow.genreId, position: above ? catalogRow.modelData.position - 1 : 0}, drop.source.genreRevision)
                                drop.acceptProposedAction()
                            }
                        }
                    }
                }
            }
            ColumnLayout {
                Layout.preferredWidth: 300; Layout.minimumWidth: 300; Layout.maximumWidth: 300; Layout.fillHeight: true
                Text { text: manager.selected ? "Edit definition" : "New definition"; color: Theme.textPrimary }
                GenreTextField { id: nameInput; objectName: "genreNameInput"; Layout.fillWidth: true; placeholderText: "Name"; color: Theme.textPrimary; background: Rectangle { color: Theme.surface; border.color: Theme.separator } }
                Text { visible: manager.section === "genre"; text: "Parent / Move to"; color: Theme.textSecondary }
                GenreComboBox { id: parentInput; objectName: "genreParentInput"; visible: manager.section === "genre"; Layout.fillWidth: true; model: manager.parentChoices; textRole: "path" }
                GenreTextField { id: positionInput; visible: manager.section === "genre"; text: "0"; placeholderText: "Display order"; validator: IntValidator { bottom: -100000; top: 100000 } color: Theme.textPrimary; background: Rectangle { color: Theme.surface; border.color: Theme.separator } Accessible.name: "Display order" }
                GenreTextField { id: aliasesInput; visible: manager.section === "genre"; Layout.fillWidth: true; placeholderText: "Aliases, separated by commas"; color: Theme.textPrimary; background: Rectangle { color: Theme.surface; border.color: Theme.separator } }
                GenreTextField { id: colorInput; visible: manager.section === "tag"; Layout.fillWidth: true; placeholderText: "Colour (optional, e.g. #89bf62)"; color: Theme.textPrimary; background: Rectangle { color: Theme.surface; border.color: Theme.separator } }
                ScrollView {
                    visible: manager.section === "meta"
                    Layout.fillWidth: true; Layout.preferredHeight: 160
                    Column {
                        Repeater {
                            model: manager.model.catalog.genres
                            GenreCheckBox {
                                required property var modelData
                                text: modelData.path
                                checked: manager.members.indexOf(modelData.genre_id) >= 0
                                onClicked: { let ids = manager.members.slice(); if (checked) ids.push(modelData.genre_id); else ids = ids.filter(i => i !== modelData.genre_id); manager.members = ids }
                            }
                        }
                    }
                }
                TextButton { objectName: "genreSaveDefinition"; text: "Save"; enabled: !manager.model.busy && nameInput.text.trim().length > 0; onClicked: manager.save() }
                RowLayout {
                    TextButton { text: "New"; onClicked: { manager.selected = null; nameInput.text = ""; aliasesInput.text = ""; manager.members = []; parentInput.currentIndex = 0 } }
                    TextButton { text: manager.selected && manager.selected.archived ? "Restore" : "Archive"; enabled: !!manager.selected && !manager.model.busy; onClicked: manager.model.edit(manager.section,"edit",manager.identity(manager.selected),{archived: !manager.selected.archived},manager.selected.revision) }
                    TextButton { text: "Delete"; enabled: !!manager.selected && !manager.model.busy; onClicked: manager.model.edit(manager.section,"delete",manager.identity(manager.selected),{},manager.selected.revision) }
                }
                TextButton { text: "Favourite"; visible: manager.section === "genre"; enabled: !!manager.selected && !manager.model.busy; onClicked: manager.model.toggleFavourite(manager.selected.genre_id) }
                Item { Layout.fillHeight: true }
                ColumnLayout {
                    objectName: "genreAdvancedControls"
                    visible: manager.advancedAllowed && manager.section === "genre"
                    Text { text: "Library > Genres > Advanced"; color: Theme.textSecondary }
                    Text { text: "Delete the selected subtree and its assignments. A verified backup is created first."; Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Theme.textSecondary }
                    GenreTextField { id: confirm; Layout.fillWidth: true; placeholderText: manager.selected ? "Type " + manager.selected.path : "Select a genre" }
                    TextButton { text: "Delete subtree"; enabled: manager.selected && confirm.text === manager.selected.path && !manager.model.busy; onClicked: { manager.model.edit("genre","force_delete",manager.selected.genre_id,{confirmation:manager.selected.genre_id},manager.selected.revision); confirm.text = "" } }
                }
            }
        }
        Text { objectName: "genreSaveStatus"; text: manager.model.message; color: Theme.textSecondary; Layout.fillWidth: true; wrapMode: Text.WordWrap }
    }
}
