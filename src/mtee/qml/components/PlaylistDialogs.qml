import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

Item {
    id: dialogs
    required property var workspace
    readonly property var model: workspace.playlistModel
    property string action: ""
    property string identity: ""
    property string importUrl: ""
    property var tracks: []
    property int version: 0
    property string locatePlaylist: ""
    property bool completeExport: false
    function show(mode, target, selected) {
        action = mode; identity = target; tracks = selected
        if (mode === "create") { model.createUntitled(target, selected); return }
        if (mode === "cover") { cover.open(); return }
        if (mode === "import") { importer.open(); return }
        if (mode === "locate") {
            const groups = workspace.groups
            locatePlaylist = groups[workspace.activeGroup].active.split(":")[1]
            locator.open(); return
        }
        if (mode === "resume") { resumes.open(); return }
        const detail = model.details(target)
        version = detail.version || 0
        name.text = mode === "edit" ? detail.name || "" : mode === "create" ? "New playlist" : mode === "renameFolder" ? (model.folders.find(f => f.id === target) || {}).name || "" : ""
        description.text = mode === "edit" ? detail.description || "" : ""
        chooser.currentIndex = 0
        form.open()
        name.forceActiveFocus()
        name.selectAll()
    }
    Connections {
        target: dialogs.workspace
        function onPlaylistCreationRequested(ids) { dialogs.model.createUntitled("", ids) }
    }
    Connections {
        target: dialogs.model
        function onUiRequested(mode, target, selected) { dialogs.show(mode, target, selected) }
        function onChanged() { if (dialogs.model.ambiguity.trackIds) ambiguity.open() }
        function onImportReady() { preview.open() }
        function onCoverChanged(target) { if (target === dialogs.identity) dialogs.version = dialogs.model.details(target).version }
        function onPlaylistCreated() { preview.close(); form.close() }
    }
    FileDialog {
        id: cover
        title: "Choose playlist cover"
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp)"]
        onAccepted: dialogs.model.setCover(dialogs.identity, String(selectedFile))
    }
    FileDialog {
        id: exporter
        title: "Export playlist"
        fileMode: FileDialog.SaveFile
        nameFilters: dialogs.completeExport ? ["Playlist with audio (*.zip)"] : ["MTEE playlist (*.mteeplaylist)"]
        onAccepted: { dialogs.model.export(dialogs.identity, String(selectedFile), dialogs.completeExport); form.close() }
    }
    FileDialog {
        id: importer
        title: "Import MTEE playlist"
        nameFilters: ["MTEE playlists (*.mteeplaylist *.zip)"]
        onAccepted: {
            dialogs.importUrl = String(selectedFile)
            if (dialogs.importUrl.toLowerCase().endsWith(".zip")) destination.open()
            else dialogs.model.prepareImport(dialogs.importUrl, "")
        }
    }
    FolderDialog {
        id: destination
        title: "Choose where to extract the playlist audio"
        onAccepted: dialogs.model.prepareImport(dialogs.importUrl, String(selectedFolder))
    }
    FileDialog {
        id: locator
        title: "Locate a local audio file"
        nameFilters: ["Audio (*.wav *.mp3 *.flac *.aif *.aiff *.m4a *.ogg *.opus *.wv *.ape)"]
        onAccepted: {
            dialogs.model.locateFile(dialogs.locatePlaylist, dialogs.identity, String(selectedFile))
        }
    }
    Popup {
        id: form
        objectName: "playlistForm"
        parent: Overlay.overlay
        width: Math.min(460, parent.width - 32)
        height: fields.implicitHeight + 40
        x: (parent.width - width) / 2; y: Math.max(16, (parent.height - height) / 2)
        modal: true; focus: true; padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        contentItem: Column {
            id: fields
            spacing: 16
            Text {
                text: dialogs.action === "create" ? "New playlist" : dialogs.action === "folder" ? "New folder"
                    : dialogs.action === "edit" ? "Edit playlist" : dialogs.action === "export" ? "Export playlist"
                    : dialogs.action.indexOf("delete") === 0 ? "Delete " + (dialogs.action === "deleteFolder" ? "folder" : "playlist") + "?"
                    : dialogs.action === "renameFolder" ? "Rename folder" : "Move to folder"
                color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 24; font.weight: Font.Bold
            }
            TextField {
                id: name
                objectName: "playlistNameInput"
                width: parent.width; height: 40
                visible: ["create", "folder", "edit", "renameFolder"].indexOf(dialogs.action) >= 0
                placeholderText: "Name"; color: Theme.textPrimary; placeholderTextColor: Theme.textMuted
                font.family: Theme.fontFamily; font.pixelSize: 16
                background: Rectangle { color: Theme.editor; border.color: name.activeFocus ? Theme.focus : Theme.separator }
            }
            TextArea {
                id: description
                width: parent.width; height: 86
                visible: dialogs.action === "edit"
                placeholderText: "Description"; color: Theme.textPrimary
                font.family: Theme.fontFamily; font.pixelSize: 15
                wrapMode: TextEdit.Wrap
                background: Rectangle { color: Theme.editor; border.color: description.activeFocus ? Theme.focus : Theme.separator }
            }
            Row {
                visible: dialogs.action === "edit"
                spacing: 12
                TextButton { text: "Choose cover"; onClicked: cover.open() }
                TextButton { text: "Use mosaic"; kind: "ghost"; onClicked: dialogs.model.setCover(dialogs.identity, "") }
            }
            ComboBox {
                id: chooser
                width: parent.width
                visible: dialogs.action === "move" || dialogs.action === "moveFolder"
                model: [{id: "", name: "Playlists (root)"}].concat(Array.from(dialogs.model.folders))
                textRole: "name"
                contentItem: Text { text: chooser.displayText; color: Theme.textPrimary; font.family: Theme.fontFamily; verticalAlignment: Text.AlignVCenter; leftPadding: 12 }
                background: Rectangle { color: Theme.editor; border.color: Theme.separator }
            }
            Text {
                width: parent.width
                visible: dialogs.action.indexOf("delete") === 0 || dialogs.action === "export"
                text: dialogs.action === "deleteFolder" ? "The folder must contain no playlists or subfolders."
                    : dialogs.action === "delete" ? "Your audio files stay in the library."
                    : "Choose a lightweight backup or include exact copies of available audio files. Missing tracks keep their positions."
                wrapMode: Text.WordWrap; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 15
            }
            Row {
                visible: dialogs.action === "export"
                spacing: 12
                TextButton { text: ".mteeplaylist"; onClicked: { dialogs.completeExport = false; exporter.open() } }
                TextButton { text: "ZIP with audio"; kind: "primary"; onClicked: { dialogs.completeExport = true; exporter.open() } }
            }
            Row {
                spacing: 12
                TextButton { text: "Cancel"; kind: "ghost"; onClicked: form.close() }
                TextButton {
                    objectName: "playlistFormSave"
                    text: dialogs.action.indexOf("delete") === 0 ? "Delete" : "Save"
                    kind: "primary"
                    visible: dialogs.action !== "export"
                    onClicked: {
                        if (dialogs.action === "create") dialogs.model.create(name.text, dialogs.identity, dialogs.tracks)
                        else if (dialogs.action === "folder") dialogs.model.createFolder(name.text, dialogs.identity)
                        else if (dialogs.action === "edit") dialogs.model.edit(dialogs.identity, name.text, description.text, dialogs.version)
                        else if (dialogs.action === "renameFolder") dialogs.model.renameFolder(dialogs.identity, name.text)
                        else if (dialogs.action === "delete") dialogs.model.delete(dialogs.identity)
                        else if (dialogs.action === "deleteFolder") dialogs.model.deleteFolder(dialogs.identity)
                        else dialogs.model.move(dialogs.identity, chooser.model[chooser.currentIndex].id, dialogs.action === "moveFolder", "")
                        form.close()
                    }
                }
            }
        }
    }
    Popup {
        id: ambiguity
        parent: Overlay.overlay; width: 440; height: 190
        x: (parent.width - width) / 2; y: (parent.height - height) / 2
        modal: true; focus: true; padding: 20
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        contentItem: Column {
            spacing: 16
            Text { width: parent.width; text: "Incomplete song tags"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 22 }
            Text { width: parent.width; text: "MTEE cannot check musical duplicates for these tracks. Add them as distinct songs?"; wrapMode: Text.WordWrap; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 15 }
            Row {
                spacing: 12
                TextButton { text: "Cancel"; onClicked: { dialogs.model.confirmAmbiguity(false); ambiguity.close() } }
                TextButton { text: "Add distinct songs"; kind: "primary"; onClicked: { dialogs.model.confirmAmbiguity(true); ambiguity.close() } }
            }
        }
    }
    Popup {
        id: preview
        objectName: "playlistImportPreview"
        parent: Overlay.overlay
        width: Math.min(740, parent.width - 48); height: Math.min(600, parent.height - 48)
        x: (parent.width - width) / 2; y: (parent.height - height) / 2
        modal: true; focus: true; padding: 20
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        contentItem: Item {
            Text { id: importTitle; text: "Import " + (dialogs.model.importPreview.name || "playlist"); color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 24 }
            ListView {
                anchors.top: importTitle.bottom; anchors.topMargin: 20
                anchors.bottom: importActions.top; anchors.bottomMargin: 16
                width: parent.width; clip: true
                model: dialogs.model.importPreview.matches || []
                ScrollBar.vertical: ThinScrollBar {}
                delegate: Column {
                    required property var modelData
                    required property int index
                    width: ListView.view.width; spacing: 6
                    Text { width: parent.width; text: (index + 1) + ". " + (modelData.snapshot.title || "Unknown track") + " · " + (modelData.snapshot.artist || "") + " — " + modelData.status; color: modelData.status === "matched" ? Theme.textPrimary : Theme.textSecondary; elide: Text.ElideRight; font.family: Theme.fontFamily; font.pixelSize: 16 }
                    Repeater {
                        model: modelData.candidates || []
                        delegate: TextButton {
                            required property var modelData
                            text: "Use " + modelData.filename + " · " + modelData.artist
                            width: parent.width; kind: "ghost"; tip: modelData.path
                            property int entryIndex: parent.index
                            onClicked: dialogs.model.chooseImportMatch(entryIndex, modelData.id)
                        }
                    }
                    TextButton { visible: modelData.status !== "missing"; text: "Keep missing"; kind: "ghost"; onClicked: dialogs.model.chooseImportMatch(parent.index, "") }
                    Item { width: 1; height: 16 }
                }
            }
            Row {
                id: importActions
                anchors.bottom: parent.bottom; anchors.right: parent.right; spacing: 12
                TextButton { text: "Close"; kind: "ghost"; onClicked: preview.close() }
                TextButton { objectName: "playlistImportCreate"; text: "Create playlist"; kind: "primary"; onClicked: dialogs.model.finishImport() }
            }
        }
    }
    Popup {
        id: resumes
        parent: Overlay.overlay; width: Math.min(600, parent.width - 40); height: Math.min(460, parent.height - 40)
        x: (parent.width - width) / 2; y: (parent.height - height) / 2
        modal: true; focus: true; padding: 20
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        contentItem: Column {
            spacing: 16
            Text { text: "Resume playlist import"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 24 }
            ListView {
                width: parent.width; height: resumes.height - 120; clip: true
                model: dialogs.model.pendingImports
                ScrollBar.vertical: ThinScrollBar {}
                delegate: TextButton {
                    required property var modelData
                    width: ListView.view.width; height: 48
                    text: modelData.phase + " · " + modelData.operation_id.substring(0, 8)
                    tip: modelData.folder_path + " · " + modelData.error
                    onClicked: { dialogs.model.resumeImport(modelData.operation_id); resumes.close() }
                }
            }
            TextButton { text: "Close"; kind: "ghost"; onClicked: resumes.close() }
        }
    }
}
