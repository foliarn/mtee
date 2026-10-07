import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Window
import Mtee

// Isolated visual review. Synthetic data and actions live only in memory.
Window {
    id: root
    width: 1440; height: 900
    minimumWidth: 900; minimumHeight: 640
    visible: true
    color: Theme.chrome
    title: "MTEE · Genres — visual review 109"
    property string scene: "house"
    property string page: "tracks"
    property string collection: "House"
    property string managerSection: "Genres"
    property string dialogKind: ""
    property string notice: ""
    property string playing: "Nothing playing"
    property bool split: false
    readonly property var scenes: ["seed", "house", "jump-up", "mixed", "manager", "meta", "tags", "filters", "retained", "saving", "error", "create", "delete", "multi", "split", "narrow"]
    function applyScene() {
        dialogKind = ""
        notice = ""
        page = ["manager", "meta", "tags"].includes(scene) ? "manager" : scene === "delete" ? "settings" : "tracks"
        collection = scene === "jump-up" ? "Jump Up" : scene === "mixed" || scene === "filters" ? "Weekend selections" : "House"
        managerSection = scene === "meta" ? "Meta-families" : scene === "tags" ? "Local tags" : "Genres"
        split = scene === "split"
        if (scene === "create") dialogKind = "create"
        if (scene === "delete") dialogKind = "delete"
    }
    onSceneChanged: applyScene()

    component Label: Text {
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 14
        elide: Text.ElideRight
    }
    component Action: Button {
        id: action
        property bool accent: false
        implicitHeight: 34
        leftPadding: 12; rightPadding: 12
        contentItem: Label {
            text: action.text
            color: action.accent ? Theme.textOnColor : action.enabled ? Theme.textPrimary : Theme.textMuted
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 12
        }
        background: Rectangle {
            color: action.accent ? Theme.primary : action.hovered ? Theme.selection : Theme.surface
            border.color: action.activeFocus ? Theme.focus : Theme.separator
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 44
            color: Theme.chrome
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: 18; anchors.rightMargin: 18
                Label { text: "MTEE"; font.bold: true; font.letterSpacing: 2 }
                Label { text: "109 / VISUAL REVIEW"; color: Theme.textMuted; font.pixelSize: 11 }
                Item { Layout.fillWidth: true }
                Label { text: "Fictional data · changes reset on close"; color: Theme.textSecondary; font.pixelSize: 12 }
                ReviewCombo {
                    id: scenePicker
                    model: root.scenes
                    currentIndex: root.scenes.indexOf(root.scene)
                    onActivated: root.scene = currentText
                    implicitWidth: 130
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            spacing: 1
            Rectangle {
                Layout.preferredWidth: root.width < 1100 ? 154 : 206
                Layout.fillHeight: true
                color: Theme.sidebar
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14; spacing: 12
                    Label { text: "LIBRARY"; color: Theme.textMuted; font.pixelSize: 11; font.letterSpacing: 1.5 }
                    Repeater {
                        model: ["House", "Jump Up", "Weekend selections"]
                        Action {
                            required property string modelData
                            Layout.fillWidth: true
                            text: modelData
                            accent: root.page === "tracks" && root.collection === modelData
                            onClicked: { root.collection = modelData; root.page = "tracks"; root.scene = modelData === "House" ? "house" : modelData === "Jump Up" ? "jump-up" : "mixed" }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
                    Action { text: "Genre manager"; Layout.fillWidth: true; accent: root.page === "manager"; onClicked: root.page = "manager" }
                    Action { text: "Settings"; Layout.fillWidth: true; onClicked: root.page = "settings" }
                    Item { Layout.fillHeight: true }
                    Label { text: "LOCAL ONLY"; color: Theme.primary; font.pixelSize: 11 }
                    Label { Layout.fillWidth: true; text: "Genres and tags belong to MTEE. Audio metadata stays separate."; wrapMode: Text.WordWrap; elide: Text.ElideNone; color: Theme.textMuted; font.pixelSize: 12 }
                }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: Theme.editor
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 22; spacing: 16
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: root.page === "manager" ? "Genre manager" : root.page === "settings" ? "Library / Genres / Advanced" : root.collection; font.pixelSize: 27; font.bold: true; Layout.fillWidth: true }
                        Action { visible: root.page !== "tracks"; text: "Back to " + root.collection; onClicked: root.page = "tracks" }
                        Action { visible: root.page === "tracks"; text: root.split ? "Single panel" : "Split view"; onClicked: root.split = !root.split }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: root.page === "manager" ? "Your taxonomy · distinct-track counts across the library · sample counts" : root.page === "settings" ? "Destructive taxonomy operations are kept here, away from the sorting controls." : root.collection === "Jump Up" ? "Context: Drum & Bass   /   Jump Up folder" : root.collection === "House" ? "Context: House   /   House alone is a valid assignment" : "Playlist · mixed families · no fixed genre context"
                        color: Theme.textSecondary; font.pixelSize: 12
                    }
                    RowLayout {
                        visible: root.page === "tracks"
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 16
                        TrackPane {
                            id: mainPane
                            Layout.fillWidth: true; Layout.fillHeight: true
                            reviewScene: root.scene
                            collection: root.collection
                            compact: root.split
                            onManageRequested: root.page = "manager"
                            onCreateRequested: root.dialogKind = "create"
                            onPlayRequested: title => root.playing = title
                        }
                        Rectangle { visible: root.split; width: 1; Layout.fillHeight: true; color: Theme.separator }
                        TrackPane {
                            visible: root.split
                            Layout.fillWidth: true; Layout.fillHeight: true
                            collection: "Jump Up"; reviewScene: "jump-up"; compact: true
                            onManageRequested: root.page = "manager"
                            onCreateRequested: root.dialogKind = "create"
                            onPlayRequested: title => root.playing = title
                        }
                    }
                    ColumnLayout {
                        visible: root.page === "manager"
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 14
                        RowLayout {
                            Repeater {
                                model: ["Genres", "Meta-families", "Local tags", "Archived"]
                                Action { required property string modelData; text: modelData; accent: root.managerSection === modelData; onClicked: root.managerSection = modelData }
                            }
                            Item { Layout.fillWidth: true }
                            Action { text: "+ Create"; accent: true; onClicked: root.dialogKind = "create" }
                        }
                        Flickable {
                            id: managerScroll
                            Layout.fillWidth: true; Layout.fillHeight: true
                            contentHeight: tables.height; clip: true
                            ScrollBar.vertical: ScrollBar {}
                            WheelScrollHandler { flickable: managerScroll }
                            Column {
                                id: tables; width: parent.width; spacing: 18
                                Repeater {
                                    model: root.managerSection === "Genres" ? ["House", "UK Garage", "Drum & Bass", "Dubstep", "Techno", "Hard Dance", "Other families"] : root.managerSection === "Meta-families" ? ["Bass Music", "Hard", "Club"] : root.managerSection === "Archived" ? ["Archived definitions"] : ["Local tags"]
                                    Rectangle {
                                        id: family
                                        required property string modelData
                                        width: tables.width; height: familyBody.height + 28
                                        color: Theme.sidebar; border.color: Theme.separator
                                        property var childrenNames: root.managerSection === "Genres" ? (modelData === "House" ? ["Tech", "Bass", "Minimal", "Deep", "Disco", "French"] : modelData === "UK Garage" ? ["Speed Garage", "2-Step", "Bassline"] : modelData === "Drum & Bass" ? ["Jump Up", "Neuro", "Liquid", "Drumstep", "Rollers", "Jungle", "Minimal", "Dancefloor", "4x4"] : modelData === "Dubstep" ? ["Deep", "Tearout", "Riddim", "Brostep", "Trap", "UK Dubstep"] : modelData === "Techno" ? ["Minimal", "Hardgroove", "Hard House", "Bouncy Techno", "Trance"] : modelData === "Hard Dance" ? ["Hardstyle", "Rawstyle", "Uptempo", "Hard Techno"] : ["Dance", "Breaks", "Baile", "Rap", "Future Bass", "Pop", "Rock", "Jazz", "Classical"]) : root.managerSection === "Meta-families" ? (modelData === "Bass Music" ? ["UK Garage", "Dubstep", "Drum & Bass", "House › Bass", "Baile"] : modelData === "Hard" ? ["Hard Dance", "Techno › Hard House", "Techno › Hardgroove"] : ["House", "Techno", "UK Garage"]) : root.managerSection === "Archived" ? ["House › Lo-fi (sample)"] : ["Banger (sample)", "Calm (sample)", "Euphoric (sample)"]
                                        Column {
                                            id: familyBody; x: 14; y: 14; width: parent.width - 28
                                            RowLayout {
                                                width: parent.width; height: 42
                                                Label { text: family.modelData; font.pixelSize: 18; font.bold: true; Layout.fillWidth: true }
                                                Label { text: "Distinct tracks"; color: Theme.textMuted; font.pixelSize: 11 }
                                                Action { text: "+ Add"; onClicked: root.dialogKind = "create" }
                                            }
                                            Repeater {
                                                model: family.childrenNames
                                                Rectangle {
                                                    required property string modelData
                                                    required property int index
                                                    width: familyBody.width; height: 42
                                                    color: index % 2 ? "transparent" : Theme.editor
                                                    RowLayout {
                                                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 8
                                                        Label { text: "≡"; color: Theme.textMuted }
                                                        Label { text: modelData; Layout.fillWidth: true }
                                                        Label { visible: modelData === "Bouncy Techno"; text: "Alias: Nu Trance"; color: Theme.textSecondary; font.pixelSize: 12 }
                                                        Label { text: root.managerSection === "Archived" ? "Archived" : String(12 + index * 7); color: Theme.textSecondary; Layout.preferredWidth: 70 }
                                                        Action { text: root.managerSection === "Archived" ? "Restore" : "Edit…"; onClicked: { root.dialogKind = "edit"; root.notice = (root.managerSection === "Genres" ? family.modelData + " › " : "") + modelData } }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        visible: root.page === "settings"
                        Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18
                        Label { text: "Force delete a genre subtree"; font.pixelSize: 20; font.bold: true }
                        Label { text: "Target: House · 6 descendants · 42 distinct tracks (fictional)"; Layout.fillWidth: true }
                        Label { text: "Removes genre definitions and their assignments. Other genres and audio files are preserved.\nA verified backup is required; the operation remains recoverable."; color: Theme.textSecondary; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Action { text: "Review deletion…"; onClicked: root.dialogKind = "delete" }
                        Label { text: "Saved filters"; font.pixelSize: 20; font.bold: true }
                        Label { text: "House exploration    ·    Without brush genre (dynamic)"; color: Theme.textSecondary }
                        Action { text: "Recall sample filter"; onClicked: { root.page = "tracks"; mainPane.filterMode = 1 } }
                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: 64; color: Theme.sidebar
            RowLayout {
                anchors.fill: parent; anchors.margins: 16
                Action { text: "▶"; onClicked: root.playing = "Side streets · North Window (sample)" }
                Label { text: root.playing; Layout.fillWidth: true }
                Label { text: "Player preview · no audio loaded"; color: Theme.textMuted; font.pixelSize: 12 }
            }
        }
    }
    Rectangle {
        anchors.fill: parent; visible: root.dialogKind !== ""; color: "#BB000000"
        MouseArea { anchors.fill: parent; onClicked: root.dialogKind = "" }
        Rectangle {
            width: Math.min(560, root.width - 64); height: body.height + 48
            anchors.centerIn: parent; color: Theme.editor; border.color: Theme.separator
            MouseArea { anchors.fill: parent }
            ColumnLayout {
                id: body; x: 24; y: 24; width: parent.width - 48; spacing: 16
                Label { text: root.dialogKind === "delete" ? "Delete House and its descendants?" : root.dialogKind === "edit" ? "Edit " + root.notice : "Create genre"; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
                Label { text: root.dialogKind === "delete" ? "6 descendants · 42 tracks · sample impact" : "Parent / family"; color: Theme.textSecondary }
                ReviewCombo { id: parentPicker; visible: root.dialogKind !== "delete"; model: ["House", "Dubstep", "UK Garage", "Drum & Bass", "Techno", "Hard Dance", "No parent (new family)"]; Layout.fillWidth: true }
                TextField { id: genreName; visible: root.dialogKind !== "delete"; placeholderText: "Genre name"; text: "Lo-fi"; Layout.fillWidth: true }
                TextField { visible: root.dialogKind === "edit"; placeholderText: "Aliases (optional)"; Layout.fillWidth: true }
                Label { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: root.dialogKind === "delete" ? "Backup must succeed before deletion. Saved filters using these genres will require correction. No replacement family is assigned." : "The parent stays explicit. Creation selects the brush without assigning it to any track."; color: Theme.textSecondary; font.pixelSize: 12 }
                RowLayout {
                    Action { visible: root.dialogKind === "edit"; text: "Move to…"; onClicked: root.notice = "Choose a new parent above (preview)" }
                    Action { visible: root.dialogKind === "edit"; text: "Archive"; onClicked: { root.managerSection = "Archived"; root.dialogKind = "" } }
                    Action { visible: root.dialogKind === "edit"; text: "Delete…"; onClicked: root.notice = "Ordinary deletion refused: this sample genre is assigned to tracks." }
                }
                Label { visible: root.dialogKind === "edit"; text: root.notice; Layout.fillWidth: true; wrapMode: Text.WordWrap; font.pixelSize: 12; color: Theme.warning }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    Action { text: "Cancel"; onClicked: root.dialogKind = "" }
                    Action {
                        text: root.dialogKind === "delete" ? "Back up & delete (preview)" : "Save (preview)"
                        accent: root.dialogKind !== "delete"
                        onClicked: {
                            if (root.dialogKind === "create") { mainPane.extraBrush = (parentPicker.currentIndex === 6 ? "" : parentPicker.currentText + " › ") + genreName.text; mainPane.brush = mainPane.extraBrush }
                            root.notice = root.dialogKind === "delete" ? "Preview only: no backup or deletion performed." : "Preview saved in memory."
                            root.dialogKind = ""
                        }
                    }
                }
            }
        }
    }
}
