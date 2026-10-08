import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee

FocusScope {
    id: bar
    objectName: "genreBrushBar"
    required property var workspace
    required property var tab
    required property var trackModel
    property int groupIndex: 0
    readonly property var genres: workspace.genreModel
    readonly property string viewKey: groupIndex + ":" + tab.id
    readonly property var state: genres.preferences.views[viewKey] || ({})
    readonly property string brush: state.brush || ""
    readonly property var spec: state.filter || ({version:1,mode:"all",criteria:[]})
    readonly property var choices: Array.from(genres.catalog.genres || []).filter(g => g.assignable && ((g.path + " " + Array.from(g.aliases || []).join(" ")).toLowerCase().includes(brushSearch.text.toLowerCase())))
    readonly property var chosen: choices.find(g => g.genre_id === brush)
    readonly property var selectedIds: workspace.selectedIdsForGroup(groupIndex)
    readonly property var shortcuts: Array.from(genres.preferences.favourites || []).concat(Array.from(genres.preferences.recent || [])).filter((v,i,a) => a.indexOf(v) === i && Array.from(genres.catalog.genres || []).some(g=>g.genre_id===v && g.assignable)).slice(0,9)
    height: 182
    function setSpec(value) { genres.setFilter(viewKey,value) }
    function addCriterion(kind, id) {
        const criteria = Array.from(spec.criteria || [])
        criteria.push({kind:kind,id:id || ""})
        setSpec({version:1,mode:spec.mode,criteria:criteria})
    }
    function applySelection(enabled) { workspace.applyGenreBrush(tab.id,groupIndex,selectedIds,enabled) }
    Keys.onPressed: event => {
        if (event.key >= Qt.Key_1 && event.key <= Qt.Key_9 && !genres.busy) {
            const id = shortcuts[event.key - Qt.Key_1]
            if (id) genres.setBrush(viewKey,id)
            event.accepted = true
        } else if (event.key === Qt.Key_Z && event.modifiers & Qt.ControlModifier) {
            genres.undo(); event.accepted = true
        }
    }
    Rectangle { anchors.fill: parent; color: Theme.sidebar }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 10; spacing: 5
        RowLayout {
            Layout.fillWidth: true
            Text { text: "Genre brush"; color: Theme.textPrimary; font.family: Theme.fontFamily }
            GenreTextField {
                id: brushSearch
                objectName: "genreBrushSearch"
                Layout.preferredWidth: 160
                visible: bar.width >= 850
                placeholderText: "Find a genre or alias"
                color: Theme.textPrimary
                background: Rectangle { color: Theme.surface; border.color: parent.activeFocus ? Theme.focus : Theme.separator }
            }
            GenreComboBox {
                id: picker
                objectName: "genreBrushPicker"
                Layout.fillWidth: true
                model: bar.choices
                textRole: "path"
                currentIndex: bar.choices.findIndex(g => g.genre_id === bar.brush)
                enabled: !bar.genres.busy
                onActivated: { bar.forceActiveFocus(); bar.genres.setBrush(bar.viewKey,bar.choices[currentIndex].genre_id) }
            }
            TextButton { text: "+ Genre"; onClicked: { quickParent.currentIndex = 0; quickCreate.open() } }
            TextButton { objectName: "openGenreManager"; text: "Manager"; onClicked: manager.open() }
            TextButton { text: "Undo"; enabled: bar.genres.canUndo; onClicked: bar.genres.undo() }
        }
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 30
            contentWidth: recentRow.implicitWidth
            contentHeight: 30
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Row {
                id: recentRow
                spacing: 6
                Text { text: "Favourites / recent"; color: Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                Repeater {
                    model: bar.shortcuts
                    TextButton {
                        required property string modelData
                        required property int index
                        text: (index + 1) + " " + bar.labelFor("genre",modelData)
                        enabled: !bar.genres.busy
                        onClicked: { bar.forceActiveFocus(); bar.genres.setBrush(bar.viewKey,modelData) }
                    }
                }
            }
        }
        RowLayout {
            Text { text: bar.selectedIds.length + " selected"; color: Theme.textSecondary }
            TextButton { text: bar.width < 850 ? "Add" : "Add to selection"; enabled: bar.brush.length > 0 && bar.selectedIds.length > 0 && !bar.genres.busy; onClicked: bar.applySelection(true) }
            TextButton { text: bar.width < 850 ? "Remove" : "Remove from selection"; enabled: bar.brush.length > 0 && bar.selectedIds.length > 0 && !bar.genres.busy; onClicked: bar.applySelection(false) }
            GenreComboBox { id: tagPicker; Layout.preferredWidth: bar.width < 850 ? 100 : 150; model: bar.genres.catalog.tags; textRole: "name" }
            TextButton { text: "+ Tag"; enabled: bar.selectedIds.length > 0 && tagPicker.currentIndex >= 0 && !bar.genres.busy; onClicked: bar.workspace.applyLocalTag(bar.tab.id,bar.groupIndex,bar.selectedIds,bar.genres.catalog.tags[tagPicker.currentIndex].tag_id,true) }
            TextButton { text: "− Tag"; enabled: bar.selectedIds.length > 0 && tagPicker.currentIndex >= 0 && !bar.genres.busy; onClicked: bar.workspace.applyLocalTag(bar.tab.id,bar.groupIndex,bar.selectedIds,bar.genres.catalog.tags[tagPicker.currentIndex].tag_id,false) }
            Item { Layout.fillWidth: true }
        }
        RowLayout {
            TextButton { text: "Without brush"; enabled: !!bar.brush && !bar.genres.busy; onClicked: bar.addCriterion("without_brush","") }
            TextButton { text: "No subgenre"; enabled: !bar.genres.busy; onClicked: bar.addCriterion("no_subgenre","") }
            TextButton { text: "Filters (" + bar.spec.criteria.length + ")"; onClicked: filters.open() }
            TextButton { objectName: "genreFilterRefresh"; text: "Refresh results"; onClicked: bar.workspace.refreshGenreFilter(bar.tab.id,bar.groupIndex) }
            Item { Layout.fillWidth: true }
            TextButton { text: "Retry"; visible: bar.genres.message.indexOf("Could not save") === 0; enabled: !bar.genres.busy; onClicked: bar.genres.retry() }
            Text { text: bar.genres.message; color: Theme.textSecondary; Layout.maximumWidth: 280; elide: Text.ElideRight }
        }
    }
    GenreManager { id: manager; model: bar.genres; parent: Overlay.overlay }
    Popup {
        id: quickCreate
        objectName: "genreQuickCreate"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 420; modal: true; focus: true; padding: 20
        background: Rectangle { color: Theme.editor; border.color: Theme.separator }
        ColumnLayout {
            anchors.fill: parent
            Text { text: "New genre"; color: Theme.textPrimary; font.pixelSize: 22 }
            GenreTextField { id: quickName; objectName: "genreQuickName"; Layout.fillWidth: true; placeholderText: "Name" }
            Text { text: "Parent (explicit)"; color: Theme.textSecondary }
            GenreComboBox { id: quickParent; objectName: "genreQuickParent"; Layout.fillWidth: true; model: [{genre_id:"",path:"Root family"}].concat(bar.choices); textRole: "path" }
            TextButton { text: "Create and use brush"; enabled: quickName.text.trim().length > 0 && !bar.genres.busy; onClicked: { bar.genres.quickCreate(bar.viewKey,quickName.text,quickParent.model[quickParent.currentIndex].genre_id); quickCreate.close() } }
            TextButton { text: "Cancel"; onClicked: quickCreate.close() }
        }
    }
    Popup {
        id: filters
        objectName: "genreFilterEditor"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(620,parent.width-32); height: Math.min(640,parent.height-32)
        modal: true; focus: true; padding: 20
        background: Rectangle { color: Theme.editor; border.color: Theme.separator }
        ColumnLayout {
            anchors.fill: parent
            Text { text: "Local genre filters"; color: Theme.textPrimary; font.pixelSize: 22 }
            GenreComboBox { id: mode; model: ["All (AND)","Any (OR)"]; currentIndex: bar.spec.mode === "all" ? 0 : 1; onActivated: bar.setSpec({version:1,mode:currentIndex===0?"all":"any",criteria:Array.from(bar.spec.criteria)}) }
            ListView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                model: bar.spec.criteria
                delegate: RowLayout {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    Text { text: modelData.kind + (modelData.id ? ": " + bar.labelFor(modelData.kind,modelData.id) : ""); color: Theme.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                    TextButton { text: "Remove"; enabled: !bar.genres.busy; onClicked: { const values=Array.from(bar.spec.criteria); values.splice(index,1); bar.setSpec({version:1,mode:bar.spec.mode,criteria:values}) } }
                }
            }
            GenreComboBox { id: criterion; Layout.fillWidth: true; model: [{kind:"genre",label:"Include genre"},{kind:"exclude_genre",label:"Exclude genre"},{kind:"meta",label:"Meta-family"},{kind:"tag",label:"Local tag"},{kind:"no_genre",label:"No genre"},{kind:"no_subgenre",label:"No subgenre"},{kind:"family_only",label:"Family only"},{kind:"without_brush",label:"Without brush"}]; textRole: "label" }
            GenreComboBox {
                id: criterionValue
                Layout.fillWidth: true
                property string criterionKind: criterion.model[criterion.currentIndex].kind
                model: {
                    if (criterionKind === "meta") return Array.from(bar.genres.catalog.metas).map(m=>({id:m.meta_id,label:m.name}))
                    if (criterionKind === "tag") return Array.from(bar.genres.catalog.tags).map(t=>({id:t.tag_id,label:t.name}))
                    const protectedIds = bar.workspace.protectedGenreIds(bar.tab.id,bar.groupIndex)
                    return Array.from(bar.genres.catalog.genres).filter(g=>criterionKind !== "exclude_genre" || protectedIds.indexOf(g.genre_id)<0).map(g=>({id:g.genre_id,label:g.path}))
                }
                textRole: "label"
                visible: ["genre","exclude_genre","meta","tag"].indexOf(criterionKind)>=0
            }
            TextButton { text: "Add criterion"; enabled: !bar.genres.busy && (!criterionValue.visible || criterionValue.currentIndex >= 0); onClicked: bar.addCriterion(criterionValue.criterionKind,criterionValue.visible ? criterionValue.model[criterionValue.currentIndex].id : "") }
            RowLayout {
                GenreTextField { id: filterName; placeholderText: "Filter name"; Layout.fillWidth: true }
                TextButton { text: "Save"; enabled: filterName.text.trim().length>0 && !bar.genres.busy; onClicked: bar.genres.saveFilter(bar.viewKey,filterName.text) }
            }
            RowLayout {
                GenreComboBox { id: saved; Layout.fillWidth: true; model: Object.keys(bar.genres.preferences.named) }
                TextButton { text: "Load"; enabled: saved.currentIndex>=0 && !bar.genres.busy; onClicked: bar.genres.loadFilter(bar.viewKey,saved.currentText) }
            }
            RowLayout {
                TextButton { text: "Reset"; enabled: !bar.genres.busy; onClicked: bar.setSpec({version:1,mode:"all",criteria:[]}) }
                TextButton { text: "Close"; onClicked: filters.close() }
            }
        }
    }
    function labelFor(kind,id) {
        if (kind === "meta") { const m=Array.from(genres.catalog.metas).find(m=>m.meta_id===id); return m ? m.name : "Missing meta-family" }
        if (kind === "tag") { const t=Array.from(genres.catalog.tags).find(t=>t.tag_id===id); return t ? t.name : "Missing tag" }
        const g=Array.from(genres.catalog.genres).find(g=>g.genre_id===id)
        return g ? g.path : "Missing genre"
    }
}
