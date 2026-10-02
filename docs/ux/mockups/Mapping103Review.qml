import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import Mtee

// 103.0 review mockup. All rows and actions are synthetic and in-memory.
Window {
    id: root

    objectName: "mapping103Review"
    width: 1480
    height: 940
    minimumWidth: 760
    minimumHeight: 600
    visible: true
    title: "MTEE · Artists and Match review"
    color: Theme.chrome

    property string scene: "review"
    property string page: "review"
    property int selectedArtistIndex: 0
    property int selectedCaseIndex: 0
    property bool editing: false
    property bool batchDialogOpen: false
    property bool aliasDialogOpen: false
    property bool showNotice: false
    property string noticeText: ""
    property string reviewState: "ready"
    property string searchText: ""
    property var draftMembers: []
    property string editedTitle: ""
    property string editedCredit: ""
    property var batchSelection: ["filename-only", "unknown-mixed", "annotation-cleanup"]

    readonly property bool narrow: width < 1080
    readonly property var selectedCase: cases.count > 0
        ? cases.get(Math.max(0, Math.min(selectedCaseIndex, cases.count - 1))) : ({})
    readonly property var selectedArtist: artists.get(Math.max(0, Math.min(selectedArtistIndex, artists.count - 1)))
    readonly property color faintLine: "#252529"

    function setNotice(message) {
        noticeText = message
        showNotice = true
        noticeTimer.restart()
    }

    function loadDraft() {
        editing = false
        const members = selectedCase.artistParts ? selectedCase.artistParts.split("|") : []
        draftMembers = members
        editedTitle = selectedCase.proposedTitle || ""
        editedCredit = selectedCase.proposedArtists || ""
    }

    function applyScene() {
        page = scene === "artists" ? "artists" : "review"
        reviewState = ["empty", "loading", "error"].includes(scene) ? scene : "ready"
        batchDialogOpen = scene === "batch"
        selectedCaseIndex = 0
        if (scene === "changed") selectedCaseIndex = 7
        else if (scene === "multi") selectedCaseIndex = 4
        else if (scene === "encoding") selectedCaseIndex = 5
        if (scene === "narrow") {
            width = 940
            height = 720
        }
        loadDraft()
    }

    onSceneChanged: applyScene()
    onSelectedCaseIndexChanged: loadDraft()

    ListModel {
        id: artists
        ListElement { name: "A+"; kind: "Artist"; tracks: 12; alias: ""; profile: "No profile link"; note: "Separate artist identity" }
        ListElement { name: "Ev"; kind: "Artist"; tracks: 7; alias: ""; profile: "No profile link"; note: "Separate artist identity" }
        ListElement { name: "North Window"; kind: "Artist"; tracks: 18; alias: "N. Window"; profile: "example.invalid/north-window"; note: "Possible alias needs your decision" }
        ListElement { name: "Koda & Fable"; kind: "Collaboration"; tracks: 4; alias: ""; profile: "No profile link"; note: "Two artists · ordered credit" }
        ListElement { name: "Lena Voss"; kind: "Artist"; tracks: 3; alias: ""; profile: "No profile link"; note: "" }
        ListElement { name: "Silver Arcade"; kind: "Artist"; tracks: 9; alias: ""; profile: "No profile link"; note: "" }
        ListElement { name: "Unresolved credit · NVR"; kind: "Unresolved"; tracks: 2; alias: ""; profile: "Not an artist identity yet"; note: "Keep visible until identified" }
    }

    ListModel {
        id: cases
        ListElement {
            caseId: "filename-only"; fileName: "Moon Arcade- Glass Current (Free Download) 320kbps.wav"; folder: "Inbox / unsorted";
            currentArtists: "No artist tags"; currentTitles: "No title tags"; proposedArtists: "Moon Arcade"; artistParts: "Moon Arcade";
            proposedTitle: "Glass Current"; alternateTitles: ""; status: "Unknown artist"; reason: "A known separator shape in the file name suggests an artist and a title.";
            detail: "No existing artist or title tags. ‘Free Download’ and ‘320kbps’ are removable annotations.";
            artistKind: "Unresolved credit"; evidence: "File name only"; rename: "Glass Current.wav"; collision: "Glass Current.wav already exists in this folder.";
            warning: "Collision"; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "unknown-mixed"; fileName: "lOlA - Better Apart.mp3"; folder: "Inbox / unsorted";
            currentArtists: "—"; currentTitles: "—"; proposedArtists: "lOlA"; artistParts: "lOlA";
            proposedTitle: "Better Apart"; alternateTitles: ""; status: "Unknown artist"; reason: "The mixed-case credit is proposed from the file name; no automatic identity is created.";
            detail: "The spelling is kept as observed. Search the catalogue, create an artist, or leave unresolved.";
            artistKind: "Unresolved credit"; evidence: "File name · mixed case"; rename: "Better Apart.mp3"; collision: "No matching file name in this folder.";
            warning: ""; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "collaboration"; fileName: "Koda & Fable - Small Hours (Extended Mix).flac"; folder: "House / new";
            currentArtists: "Koda & Fable"; currentTitles: "Koda & Fable - Small Hours (Extended Mix)"; proposedArtists: "Koda & Fable"; artistParts: "Koda|Fable";
            proposedTitle: "Small Hours (Extended Mix)"; alternateTitles: ""; status: "Collaboration"; reason: "Both names remain separate, ordered artists in one collaboration credit.";
            detail: "The title prefix is removed because it matches the proposed credit. Extended Mix stays in the title.";
            artistKind: "Collaboration"; evidence: "Artist tag · title prefix"; rename: "Small Hours (Extended Mix).flac"; collision: "No matching file name in this folder.";
            warning: ""; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "possible-alias"; fileName: "N Window - Glass Shapes.mp3"; folder: "House / new";
            currentArtists: "North Window"; currentTitles: "Glass Shapes"; proposedArtists: "N Window"; artistParts: "N Window";
            proposedTitle: "Glass Shapes"; alternateTitles: ""; status: "Possible alias"; reason: "This spelling resembles ‘N. Window’; the names are not linked automatically.";
            detail: "Compare the existing artist record before choosing ‘Link alias’. A similar name is not proof.";
            artistKind: "Possible alias"; evidence: "Artist tag · catalogue resemblance"; rename: "Glass Shapes.mp3"; collision: "No matching file name in this folder.";
            warning: "Needs review"; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "multi-values"; fileName: "North Avenue & Isla - Side Road.mp3"; folder: "Breaks / recent";
            currentArtists: "North Avenue · Isla"; currentTitles: "Side Road · Side Road (Radio Edit)"; proposedArtists: "North Avenue · Isla"; artistParts: "North Avenue|Isla";
            proposedTitle: "Side Road"; alternateTitles: "Side Road (Radio Edit)"; status: "Multiple values"; reason: "All artist and title values remain available; choose the title to keep.";
            detail: "The tags contain two title values. Nothing is discarded by selecting this row.";
            artistKind: "Collaboration"; evidence: "Two artist values · two title values"; rename: "Side Road.mp3"; collision: "No matching file name in this folder.";
            warning: "2 title choices"; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "encoding"; fileName: "Caf� - No Signal.mp3"; folder: "Unsorted";
            currentArtists: "Caf�"; currentTitles: "No Signal"; proposedArtists: "Caf�"; artistParts: "Caf�";
            proposedTitle: "No Signal"; alternateTitles: ""; status: "Encoding suspect"; reason: "A replacement character appears in the source text.";
            detail: "Text is shown as read. MTEE does not guess an encoding repair.";
            artistKind: "Unresolved credit"; evidence: "Artist tag · replacement character"; rename: "No Signal.mp3"; collision: "No matching file name in this folder.";
            warning: "Encoding"; revision: "Source unchanged"; changed: false; warningEncoding: true
        }
        ListElement {
            caseId: "annotation-cleanup"; fileName: "Lena Voss - Blue Hour (Free Download) [CAT-041] 320kbps.wav"; folder: "Breaks / new";
            currentArtists: "Lena Voss"; currentTitles: "Lena Voss - Blue Hour (Free Download) [CAT-041] 320kbps"; proposedArtists: "Lena Voss"; artistParts: "Lena Voss";
            proposedTitle: "Blue Hour"; alternateTitles: ""; status: "Annotations removed"; reason: "The artist prefix, promo note, catalogue code and bitrate are excluded from the clean title.";
            detail: "No version marker is present. A musical version would remain, for example ‘Blue Hour (VIP)’";
            artistKind: "Artist"; evidence: "Artist tag · title tag"; rename: "Blue Hour.wav"; collision: "No matching file name in this folder.";
            warning: ""; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "changed-file"; fileName: "Silver Arcade - Static Bloom.mp3"; folder: "House / recent";
            currentArtists: "Silver Arcade"; currentTitles: "Static Bloom"; proposedArtists: "Silver Arcade"; artistParts: "Silver Arcade";
            proposedTitle: "Static Bloom"; alternateTitles: ""; status: "File changed"; reason: "The source file changed after this proposal was prepared.";
            detail: "Review the new file details before saving a decision. Previous proposal remains visible for comparison.";
            artistKind: "Artist"; evidence: "Artist tag · title tag"; rename: "Static Bloom.mp3"; collision: "No matching file name in this folder.";
            warning: "Stale proposal"; revision: "Changed since proposal"; changed: true; warningEncoding: false
        }
        ListElement {
            caseId: "no-evidence"; fileName: "untitled-219.mp3"; folder: "Inbox / unsorted";
            currentArtists: "No artist tags"; currentTitles: "No title tags"; proposedArtists: "No artist suggestion"; artistParts: "";
            proposedTitle: ""; alternateTitles: ""; status: "No evidence"; reason: "No tags or reliable artist/title split are available.";
            detail: "Leave unresolved, skip this file, or edit it manually. Other files can still be reviewed.";
            artistKind: "Unresolved credit"; evidence: "No usable evidence"; rename: "No title suggestion"; collision: "";
            warning: "Unresolved"; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
        ListElement {
            caseId: "a-plus"; fileName: "A+ - Lighter (Dubplate Extended Remix).mp3"; folder: "Bass / recent";
            currentArtists: "A+"; currentTitles: "A+ - Lighter (Dubplate Extended Remix)"; proposedArtists: "A+"; artistParts: "A+";
            proposedTitle: "Lighter (Dubplate Extended Remix)"; alternateTitles: ""; status: "Version kept"; reason: "A+ stays an artist. The title prefix is removed and the full version credit remains.";
            detail: "The version is part of the proposed title. No remix artist is substituted for the main artist.";
            artistKind: "Artist"; evidence: "Artist tag · title prefix"; rename: "Lighter (Dubplate Extended Remix).mp3"; collision: "No matching file name in this folder.";
            warning: ""; revision: "Source unchanged"; changed: false; warningEncoding: false
        }
    }

    component AppButton: Item {
        id: button
        property string label: "Button"
        property color fill: "transparent"
        property color ink: Theme.textPrimary
        property color stroke: Theme.separator
        property bool accent: false
        property bool enabled: true
        signal clicked()
        implicitWidth: textLabel.implicitWidth + 26
        implicitHeight: 34
        opacity: enabled ? 1 : 0.45

        Rectangle {
            anchors.fill: parent
            color: mouse.containsMouse && button.enabled ? (button.accent ? Theme.primaryHover : Theme.selection) : button.fill
            border.width: 1
            border.color: button.accent ? Theme.primary : button.stroke
        }
        Text {
            id: textLabel
            anchors.centerIn: parent
            text: button.label
            color: button.accent && mouse.containsMouse ? Theme.textOnColor : button.ink
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: button.accent ? Font.DemiBold : Font.Medium
        }
        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: button.enabled
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: button.clicked()
        }
    }

    component SearchBox: Rectangle {
        id: search
        property alias text: input.text
        property string placeholder: "Search"
        implicitHeight: 34
        color: Theme.editor
        border.width: 1
        border.color: input.activeFocus ? Theme.focus : Theme.separator
        Row {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 8
            spacing: 8
            Icon { name: "search"; size: 16; color: Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
            TextInput {
                id: input
                width: parent.width - 26
                height: parent.height
                verticalAlignment: TextInput.AlignVCenter
                color: Theme.textPrimary
                selectionColor: Theme.primary
                selectedTextColor: Theme.textOnColor
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                clip: true
                Text { anchors.fill: parent; verticalAlignment: Text.AlignVCenter; text: search.placeholder; color: Theme.textMuted; font: input.font; visible: !input.text && !input.activeFocus }
            }
        }
    }

    component StateTag: Rectangle {
        id: tag
        property string label: "State"
        property color tint: Theme.textSecondary
        implicitWidth: tagText.implicitWidth + 14
        implicitHeight: 22
        color: Qt.rgba(tint.r, tint.g, tint.b, 0.10)
        border.width: 1
        border.color: Qt.rgba(tint.r, tint.g, tint.b, 0.30)
        Text {
            id: tagText
            anchors.centerIn: parent
            text: tag.label
            color: tag.tint
            font.family: Theme.fontFamily
            font.pixelSize: 10
            font.weight: Font.Medium
        }
    }

    Rectangle {
        id: titleBar
        anchors.top: parent.top
        width: parent.width
        height: 32
        color: Theme.chrome
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Text { text: "MTEE"; color: Theme.primary; font.family: Theme.displayFontFamily; font.pixelSize: 12; font.weight: Font.Bold }
            Rectangle { width: 1; height: 16; color: Theme.separator; anchors.verticalCenter: parent.verticalCenter }
            Text { text: root.page === "artists" ? "Artists" : "Match review"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
        }
        Row {
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Repeater {
                model: ["win-minimize", "win-maximize", "win-close"]
                delegate: Rectangle {
                    required property string modelData
                    width: 28; height: 26; color: mouse.containsMouse ? Theme.surface : "transparent"
                    Icon { anchors.centerIn: parent; name: modelData; color: Theme.textSecondary; size: 13 }
                    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: if (modelData === "win-close") root.close() }
                }
            }
        }
    }

    Rectangle {
        id: activityRail
        anchors.top: titleBar.bottom
        anchors.bottom: parent.bottom
        width: Theme.activityBarWidth
        color: Theme.chrome

        Column {
            anchors.top: parent.top
            width: parent.width
            Repeater {
                model: [
                    { "id": "library", "icon": "explorer", "label": "Library" },
                    { "id": "artists", "icon": "music", "label": "Artists" },
                    { "id": "review", "icon": "list", "label": "Match review" },
                    { "id": "playlists", "icon": "playlists", "label": "Playlists" },
                    { "id": "tasks", "icon": "tasks", "label": "Tasks" }
                ]
                delegate: Item {
                    required property var modelData
                    width: Theme.activityBarWidth; height: Theme.activityBarWidth
                    Rectangle { visible: (modelData.id === "artists" && root.page === "artists") || (modelData.id === "review" && root.page === "review"); width: 2; height: parent.height; color: Theme.primary }
                    Icon { anchors.centerIn: parent; name: modelData.icon; color: ((modelData.id === "artists" && root.page === "artists") || (modelData.id === "review" && root.page === "review")) ? Theme.textPrimary : Theme.textMuted; size: 22 }
                    MouseArea { anchors.fill: parent; hoverEnabled: true; onClicked: if (modelData.id === "artists") root.page = "artists"; else if (modelData.id === "review") root.page = "review" }
                }
            }
        }
        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.separator }
        Text { anchors.bottom: parent.bottom; anchors.bottomMargin: 13; anchors.horizontalCenter: parent.horizontalCenter; text: "M"; color: Theme.textMuted; font.family: Theme.displayFontFamily; font.pixelSize: 13; font.weight: Font.Bold }
    }

    Rectangle {
        id: contextSidebar
        anchors.top: titleBar.bottom
        anchors.bottom: parent.bottom
        anchors.left: activityRail.right
        width: root.narrow ? 0 : 230
        color: Theme.sidebar
        visible: !root.narrow

        Column {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 14
            anchors.topMargin: 22
            spacing: 16
            Text { text: root.page === "artists" ? "CATALOGUE" : "REVIEW QUEUE"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 0.8 }
            SearchBox { width: parent.width; placeholder: root.page === "artists" ? "Find an artist" : "Find a file or artist" }
            Column {
                width: parent.width
                spacing: 3
                Repeater {
                    model: root.page === "artists"
                        ? [{label:"All artists", count:"1,284", active:true}, {label:"Needs review", count:"23", active:false}, {label:"Collaborations", count:"41", active:false}, {label:"Unresolved credits", count:"8", active:false}]
                        : [{label:"Needs review", count:"18", active:true}, {label:"Conflicts", count:"6", active:false}, {label:"Unknown artists", count:"7", active:false}, {label:"Changed files", count:"2", active:false}, {label:"Accepted", count:"—", active:false}, {label:"Rejected", count:"—", active:false}]
                    delegate: Rectangle {
                        required property var modelData
                        width: parent.width; height: 34; color: modelData.active ? Theme.selection : mouse.containsMouse ? Theme.surface : "transparent"
                        Row {
                            anchors.fill: parent; anchors.leftMargin: 9; anchors.rightMargin: 9; spacing: 8
                            Rectangle { width: 6; height: 6; color: modelData.active ? Theme.primary : Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData.label; color: modelData.active ? Theme.textPrimary : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 54; elide: Text.ElideRight }
                            Text { text: modelData.count; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                        }
                        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: if (modelData.label === "Collaborations") root.selectedArtistIndex = 3; else if (modelData.label === "Unresolved credits") root.selectedArtistIndex = 6; else if (modelData.label === "Changed files") root.selectedCaseIndex = 7 }
                    }
                }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.separator }
            Text { text: "EXAMPLE DATA"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.weight: Font.DemiBold; font.letterSpacing: 0.8 }
            Text { width: parent.width; wrapMode: Text.WordWrap; text: "Names and counts are fictional. Nothing here is linked to your library."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; lineHeight: 1.25 }
        }
    }

    Rectangle {
        id: mainArea
        anchors.top: titleBar.bottom
        anchors.bottom: parent.bottom
        anchors.left: contextSidebar.visible ? contextSidebar.right : activityRail.right
        anchors.right: parent.right
        color: Theme.editor

        // ARTISTS
        Item {
            anchors.fill: parent
            visible: root.page === "artists"
            Column {
                anchors.fill: parent
                spacing: 0
                Rectangle {
                    width: parent.width; height: 78; color: Theme.editor
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 26; anchors.rightMargin: 24; spacing: 12
                        ColumnLayout {
                            spacing: 4
                            Text { text: "Artists"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 25; font.weight: Font.Bold }
                            Text { text: "Names, aliases, collaborations and profile links"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        }
                        Item { Layout.fillWidth: true }
                        StateTag { label: "EXAMPLE DATA"; tint: Theme.textMuted }
                        AppButton { label: "New artist"; fill: Theme.primary; ink: Theme.textOnColor; accent: true; onClicked: root.setNotice("New artist creation is shown only in this prototype.") }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
                }
                RowLayout {
                    width: parent.width; height: parent.height - 78; spacing: 0
                    Rectangle {
                        Layout.preferredWidth: root.narrow ? parent.width : 370
                        Layout.fillWidth: root.narrow
                        Layout.fillHeight: true
                        color: Theme.editor
                        Column {
                            anchors.fill: parent; anchors.margins: 18; spacing: 12
                            SearchBox { id: artistSearch; width: parent.width; placeholder: "Search artists and aliases" }
                            Row {
                                spacing: 6
                                StateTag { label: "All"; tint: Theme.primary }
                                Text { text: "Artist  ·  Collaboration  ·  Unresolved"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
                            }
                            ListView {
                                id: artistList
                                width: parent.width; height: parent.height - 78
                                model: artists
                                clip: true
                                spacing: 2
                                delegate: Rectangle {
                                    required property int index
                                    required property string name
                                    required property string kind
                                    required property int tracks
                                    width: artistList.width; height: 56
                                    color: root.selectedArtistIndex === index ? Theme.selection : mouse.containsMouse ? Theme.surface : "transparent"
                                    Rectangle { visible: root.selectedArtistIndex === index; width: 2; height: parent.height; color: Theme.primary }
                                    Column {
                                        anchors.left: parent.left; anchors.leftMargin: 12; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                                        Row {
                                            width: parent.width; spacing: 8
                                            Text { text: name; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13; font.weight: Font.Medium; width: parent.width - kindLabel.implicitWidth - 8; elide: Text.ElideRight }
                                            Text { id: kindLabel; text: kind; color: kind === "Collaboration" ? Theme.secondary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                        }
                                        Text { text: tracks + (tracks === 1 ? " linked track" : " linked tracks"); color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                    }
                                    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: { root.selectedArtistIndex = index; if (name === "Koda & Fable") root.selectedArtistIndex = 3 } }
                                }
                            }
                        }
                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.separator }
                    }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Flickable {
                            anchors.fill: parent; contentWidth: width; contentHeight: artistDetail.implicitHeight + 44; clip: true
                            Column {
                                id: artistDetail
                                width: parent.width - 52; x: 26; y: 24; spacing: 18
                                Row {
                                    spacing: 14
                                    Rectangle { width: 58; height: 58; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                        Icon { anchors.centerIn: parent; name: selectedArtist.kind === "Collaboration" ? "playlists" : "music"; size: 25; color: Theme.primary }
                                    }
                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                        Text { text: selectedArtist.name; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 22; font.weight: Font.Bold }
                                        Row { spacing: 8; StateTag { label: selectedArtist.kind; tint: selectedArtist.kind === "Collaboration" ? Theme.secondary : Theme.primary } Text { text: selectedArtist.tracks + " example tracks"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter } }
                                    }
                                    AppButton { label: "Edit name"; onClicked: root.setNotice("Name editing is a prototype interaction; nothing is saved.") }
                                    AppButton { label: "…"; onClicked: root.setNotice("More artist actions are reserved for review.") }
                                }
                                Rectangle { width: parent.width; height: 1; color: Theme.separator }

                                RowLayout {
                                    width: parent.width; spacing: 24
                                    ColumnLayout {
                                        Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 8
                                        Text { text: selectedArtist.kind === "Collaboration" ? "Collaboration members" : "Aliases"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        Rectangle {
                                            Layout.fillWidth: true; implicitHeight: selectedArtist.kind === "Collaboration" ? 80 : 82; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                            Column {
                                                anchors.fill: parent; anchors.margins: 13; spacing: 8
                                                Text { text: selectedArtist.kind === "Collaboration" ? "Ordered artist credit" : (selectedArtist.alias.length ? "Possible alias · not linked" : "No aliases linked"); color: selectedArtist.alias.length ? Theme.warning : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                                                Row {
                                                    spacing: 7
                                                    visible: selectedArtist.kind === "Collaboration"
                                                    StateTag { label: "Koda"; tint: Theme.textPrimary }
                                                    Text { text: "&"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 12 }
                                                    StateTag { label: "Fable"; tint: Theme.textPrimary }
                                                }
                                                Text { visible: selectedArtist.kind !== "Collaboration" && selectedArtist.alias.length; text: selectedArtist.alias; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 13 }
                                                Text { visible: selectedArtist.kind !== "Collaboration" && !selectedArtist.alias.length; text: "Choose an alias to attach explicitly."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11 }
                                            }
                                        }
                                        RowLayout {
                                            spacing: 8
                                            AppButton { label: selectedArtist.kind === "Collaboration" ? "Edit members" : "Link alias…"; onClicked: root.aliasDialogOpen = true }
                                            Text { text: "No automatic merges"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 8
                                        Text { text: "Profile links"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                        Rectangle {
                                            Layout.fillWidth: true; implicitHeight: 82; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                            Column {
                                                anchors.fill: parent; anchors.margins: 13; spacing: 7
                                                Row { spacing: 7; Icon { name: "music"; size: 14; color: Theme.textMuted } Text { text: "SoundCloud"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 } }
                                                Text { text: selectedArtist.profile; color: selectedArtist.profile.startsWith("example") ? Theme.primary : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight }
                                                Text { text: "Links are entered manually · not checked online"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                            }
                                        }
                                        AppButton { label: "Add profile link"; onClicked: root.setNotice("Profile link entry is simulated; no network request is made.") }
                                    }
                                }

                                Text { text: "Linked tracks"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                Column {
                                    width: parent.width; spacing: 1
                                    Repeater {
                                        model: selectedArtist.kind === "Collaboration"
                                            ? ["Small Hours (Extended Mix)", "Quiet Hours", "Blue Lantern"]
                                            : ["Glass Shapes", "Long Way Home", "Soft Signal"]
                                        delegate: Rectangle {
                                            required property string modelData
                                            required property int index
                                            width: parent.width; height: 48; color: index % 2 ? Theme.surface : "#1D1D20"
                                            Row {
                                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12; spacing: 10
                                                Rectangle { width: 27; height: 27; color: Theme.selection; anchors.verticalCenter: parent.verticalCenter; Icon { anchors.centerIn: parent; name: "music"; size: 14; color: Theme.textMuted } }
                                                Column { anchors.verticalCenter: parent.verticalCenter; spacing: 3; Text { text: modelData; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12 } Text { text: "Example file · tags not changed"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 } }
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    width: parent.width; height: 50; color: "transparent"
                                    Row { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; spacing: 7; Icon { name: "info"; size: 14; color: Theme.textMuted } Text { text: "Artist artwork is not included in this review."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter } }
                                }
                            }
                        }
                    }
                }
            }
        }

        // MATCH REVIEW
        Item {
            anchors.fill: parent
            visible: root.page === "review"
            Column {
                anchors.fill: parent; spacing: 0
                Rectangle {
                    width: parent.width; height: 78; color: Theme.editor
                    RowLayout {
                        anchors.fill: parent; anchors.leftMargin: 26; anchors.rightMargin: 24; spacing: 12
                        ColumnLayout {
                            spacing: 4
                            Text { text: "Match review"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 25; font.weight: Font.Bold }
                            Text { text: "Review proposed artist and title changes. Files stay untouched."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                        }
                        Item { Layout.fillWidth: true }
                        StateTag { label: "EXAMPLE DATA"; tint: Theme.textMuted }
                        AppButton { label: "Recalculate"; onClicked: { root.reviewState = "loading"; recalcTimer.restart() } }
                        AppButton { label: "Accept selected"; fill: Theme.primary; ink: Theme.textOnColor; accent: true; enabled: root.batchSelection.length > 0; onClicked: root.batchDialogOpen = true }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
                }
                RowLayout {
                    width: parent.width; height: 48; spacing: 8
                    anchors.leftMargin: 20; anchors.rightMargin: 20
                    SearchBox { Layout.preferredWidth: root.narrow ? 170 : 240; placeholder: "Search files and artists"; onTextChanged: root.searchText = text }
                    AppButton { label: "All statuses  ▾"; onClicked: root.setNotice("Status filters are shown in the left review rail.") }
                    AppButton { label: "Sort: Needs review  ▾"; onClicked: root.setNotice("Sort menu is illustrative.") }
                    Item { Layout.fillWidth: true }
                    Text { text: "18 need review"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                }
                Rectangle { width: parent.width; height: 1; color: Theme.separator }

                RowLayout {
                    width: parent.width; height: parent.height - 127; spacing: 0
                    Rectangle {
                        Layout.preferredWidth: root.narrow ? 0 : 354; Layout.fillHeight: true; color: Theme.editor; visible: !root.narrow
                        Column {
                            anchors.fill: parent; anchors.margins: 10; spacing: 2
                            Repeater {
                                model: cases
                                delegate: Rectangle {
                                    required property int index
                                    required property string caseId
                                    required property string fileName
                                    required property string proposedArtists
                                    required property string proposedTitle
                                    required property string status
                                    required property string warning
                                    required property bool changed
                                    width: parent.width; height: 64
                                    property bool selectedForBatch: root.batchSelection.indexOf(caseId) >= 0
                                    visible: !root.searchText.length || (fileName + proposedArtists + proposedTitle + status).toLowerCase().includes(root.searchText.toLowerCase())
                                    color: root.selectedCaseIndex === index ? Theme.selection : rowMouse.containsMouse ? Theme.surface : "transparent"
                                    Rectangle { visible: root.selectedCaseIndex === index; width: 2; height: parent.height; color: Theme.primary }
                                    Rectangle {
                                        x: 11; y: 22; width: 15; height: 15
                                        color: selectedForBatch ? Theme.primary : "transparent"
                                        border.width: 1; border.color: selectedForBatch ? Theme.primary : Theme.textMuted
                                        Icon { anchors.centerIn: parent; visible: selectedForBatch; name: "check"; size: 11; color: Theme.textOnColor }
                                        MouseArea { anchors.fill: parent; onClicked: { let items = root.batchSelection.slice(0); const at = items.indexOf(caseId); if (at >= 0) items.splice(at, 1); else items.push(caseId); root.batchSelection = items } }
                                    }
                                    Column {
                                        x: 36; y: 10; width: parent.width - 46; spacing: 4
                                        Text { width: parent.width; text: fileName; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; elide: Text.ElideMiddle }
                                        Row {
                                            width: parent.width; spacing: 7
                                            Text { text: status; color: changed ? Theme.warning : Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                            Text { text: "·  " + proposedArtists + (proposedTitle.length ? " — " + proposedTitle : ""); color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; width: parent.width - 68; elide: Text.ElideRight }
                                        }
                                    }
                                    MouseArea { id: rowMouse; anchors.fill: parent; z: -1; hoverEnabled: true; onClicked: { root.selectedCaseIndex = index; root.loadDraft() } }
                                }
                            }
                        }
                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.separator }
                    }

                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Column {
                            anchors.fill: parent; spacing: 0
                            Row {
                                visible: root.narrow; width: parent.width; height: 48; spacing: 8
                                anchors.leftMargin: 16; anchors.rightMargin: 16
                                Text { text: "Review file"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter }
                                Rectangle {
                                    width: parent.width - 120; height: 32; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                    Text { anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; verticalAlignment: Text.AlignVCenter; text: selectedCase.fileName || "Select a review file"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 10; elide: Text.ElideMiddle }
                                    MouseArea { anchors.fill: parent; onClicked: { root.selectedCaseIndex = (root.selectedCaseIndex + 1) % cases.count; root.loadDraft() } }
                                }
                            }

                            StackLayout {
                                width: parent.width; height: parent.height - (root.narrow ? 48 : 0)
                                currentIndex: root.reviewState === "empty" ? 1 : (root.reviewState === "loading" ? 2 : (root.reviewState === "error" ? 3 : 0))
                                Item {
                                    Flickable {
                                        anchors.fill: parent; contentWidth: width; contentHeight: reviewDetail.implicitHeight + 34; clip: true
                                        Column {
                                            id: reviewDetail
                                            width: parent.width - 40; x: 20; y: 16; spacing: 14

                                            Row {
                                                width: parent.width; spacing: 10
                                                Column {
                                                    width: parent.width - 150; spacing: 4
                                                    Text { width: parent.width; text: selectedCase.fileName || "No file selected"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; elide: Text.ElideMiddle }
                                                    Text { text: selectedCase.folder || ""; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                                }
                                                Item { width: parent.width - parent.children[0].width - 150; height: 1 }
                                                StateTag { label: selectedCase.status || "Needs review"; tint: selectedCase.changed ? Theme.warning : (selectedCase.warningEncoding ? Theme.danger : Theme.secondary) }
                                            }

                                            Rectangle {
                                                visible: selectedCase.changed
                                                width: parent.width; height: 54; color: "#302714"; border.width: 1; border.color: "#684C14"
                                                Row { anchors.fill: parent; anchors.leftMargin: 12; spacing: 9; Icon { name: "alert"; size: 15; color: Theme.warning; anchors.verticalCenter: parent.verticalCenter } Column { anchors.verticalCenter: parent.verticalCenter; spacing: 3; Text { text: "File changed since proposal"; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold } Text { text: "Recheck the source before saving a decision."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10 } } }
                                            }

                                            RowLayout {
                                                width: parent.width; spacing: 12
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Text { text: "Current tags"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                                    Rectangle {
                                                        Layout.fillWidth: true; implicitHeight: 103; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                                        Column { anchors.fill: parent; anchors.margins: 11; spacing: 9
                                                            Row { width: parent.width; spacing: 8; Text { text: "Artist"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; width: 42 } Text { text: selectedCase.currentArtists || "—"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; wrapMode: Text.Wrap; width: parent.width - 50 } }
                                                            Row { width: parent.width; spacing: 8; Text { text: "Title"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; width: 42 } Text { text: selectedCase.currentTitles || "—"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; wrapMode: Text.Wrap; width: parent.width - 50 } }
                                                            Text { text: selectedCase.revision || ""; color: selectedCase.changed ? Theme.warning : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9 }
                                                        }
                                                    }
                                                }
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Row { width: parent.width; spacing: 7; Text { text: "Proposed decision"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold } Text { text: "Not saved"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 } }
                                                    Rectangle {
                                                        Layout.fillWidth: true; implicitHeight: 103; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                                        Column { anchors.fill: parent; anchors.margins: 10; spacing: 7
                                                            Text { text: "Artist credit"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9; visible: false }
                                                            Row {
                                                                width: parent.width; spacing: 4
                                                                Text { text: "Artist"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; width: 42; anchors.verticalCenter: parent.verticalCenter }
                                                                TextInput { id: artistCreditInput; width: parent.width - 50; height: 23; text: root.editing ? root.editedCredit : (selectedCase.proposedArtists || ""); onTextEdited: if (root.editing) root.editedCredit = text; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; selectByMouse: true; selectionColor: Theme.primary; selectedTextColor: Theme.textOnColor; readOnly: !root.editing; clip: true; Rectangle { anchors.fill: parent; z: -1; color: root.editing ? Theme.editor : "transparent"; border.width: root.editing ? 1 : 0; border.color: Theme.focus } }
                                                            }
                                                            Row {
                                                                width: parent.width; spacing: 4
                                                                Text { text: "Title"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; width: 42; anchors.verticalCenter: parent.verticalCenter }
                                                                TextInput { id: titleInput; width: parent.width - 50; height: 23; text: root.editing ? root.editedTitle : (selectedCase.proposedTitle || ""); onTextEdited: if (root.editing) root.editedTitle = text; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; selectByMouse: true; selectionColor: Theme.primary; selectedTextColor: Theme.textOnColor; readOnly: !root.editing; clip: true; Rectangle { anchors.fill: parent; z: -1; color: root.editing ? Theme.editor : "transparent"; border.width: root.editing ? 1 : 0; border.color: Theme.focus } }
                                                            }
                                                            Row { spacing: 5; StateTag { label: selectedCase.artistKind || "Unresolved credit"; tint: selectedCase.artistKind === "Collaboration" ? Theme.secondary : Theme.textSecondary } Text { text: "Identity not confirmed"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9; anchors.verticalCenter: parent.verticalCenter } }
                                                        }
                                                    }
                                                }
                                            }

                                            RowLayout {
                                                width: parent.width; spacing: 12
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Row { spacing: 7; Text { text: "Artist order"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold } Text { text: "Drag or use arrows when editing"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9 } }
                                                    Column {
                                                        Layout.fillWidth: true; spacing: 3
                                                        Repeater {
                                                            model: root.draftMembers
                                                            delegate: Rectangle {
                                                                required property string modelData
                                                                required property int index
                                                                width: parent.width; height: 34; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                                                Row {
                                                                    anchors.fill: parent; anchors.leftMargin: 9; anchors.rightMargin: 4; spacing: 7
                                                                    Icon { name: "list"; size: 12; color: Theme.textMuted; anchors.verticalCenter: parent.verticalCenter }
                                                                    Text { text: modelData; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 120; elide: Text.ElideRight }
                                                                    Item { width: Math.max(0, parent.width - 160); height: 1 }
                                                                     Item { width: 16; height: 20; anchors.verticalCenter: parent.verticalCenter; Icon { anchors.centerIn: parent; name: "arrow-up"; size: 13; color: root.editing ? Theme.textSecondary : Theme.textMuted } MouseArea { anchors.fill: parent; enabled: root.editing && index > 0; onClicked: { let a=root.draftMembers.slice(0); const v=a[index-1]; a[index-1]=a[index]; a[index]=v; root.draftMembers=a; root.editedCredit=a.join(" & ") } } }
                                                                     Item { width: 16; height: 20; anchors.verticalCenter: parent.verticalCenter; Icon { anchors.centerIn: parent; name: "arrow-down"; size: 13; color: root.editing ? Theme.textSecondary : Theme.textMuted } MouseArea { anchors.fill: parent; enabled: root.editing && index < root.draftMembers.length-1; onClicked: { let a=root.draftMembers.slice(0); const v=a[index+1]; a[index+1]=a[index]; a[index]=v; root.draftMembers=a; root.editedCredit=a.join(" & ") } } }
                                                                     Item { width: 16; height: 20; anchors.verticalCenter: parent.verticalCenter; Icon { anchors.centerIn: parent; name: "close"; size: 12; color: root.editing ? Theme.danger : Theme.textMuted } MouseArea { anchors.fill: parent; enabled: root.editing; onClicked: { let a=root.draftMembers.slice(0); a.splice(index,1); root.draftMembers=a; root.editedCredit=a.join(" & ") } } }
                                                                }
                                                            }
                                                        }
                                                        Text { visible: root.draftMembers.length === 0; text: "No resolved artist selected. Keep the source credit unresolved or add an artist."; color: Theme.warning; font.family: Theme.fontFamily; font.pixelSize: 10; wrapMode: Text.WordWrap }
                                                    }
                                                    AppButton { visible: root.editing; label: "+ Add artist"; onClicked: { let a=root.draftMembers.slice(0); a.push("New artist"); root.draftMembers=a; root.editedCredit=a.join(" & ") } }
                                                }
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Text { text: "Why this was suggested"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                                    Rectangle {
                                                        Layout.fillWidth: true; implicitHeight: 74; color: Theme.surface; border.width: 1; border.color: Theme.separator
                                                        Column { anchors.fill: parent; anchors.margins: 11; spacing: 5
                                                            Text { width: parent.width; text: selectedCase.reason || "No matching evidence"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 10; wrapMode: Text.WordWrap }
                                                            Text { width: parent.width; text: selectedCase.detail || "No additional source details."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10; wrapMode: Text.WordWrap }
                                                        }
                                                    }
                                                }
                                            }

                                            RowLayout {
                                                width: parent.width; spacing: 12
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Text { text: "Rename preview"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                                    Rectangle {
                                                        Layout.fillWidth: true; implicitHeight: 60; color: selectedCase.warning === "Collision" ? "#302714" : Theme.surface; border.width: 1; border.color: selectedCase.warning === "Collision" ? "#684C14" : Theme.separator
                                                        Column { anchors.fill: parent; anchors.margins: 10; spacing: 4
                                                            Text { text: selectedCase.rename || "No title suggestion"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 12; font.weight: Font.Medium }
                                                            Text { width: parent.width; text: selectedCase.collision || "No collision detected in this example."; color: selectedCase.warning === "Collision" ? Theme.warning : Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 9; wrapMode: Text.WordWrap }
                                                        }
                                                    }
                                                }
                                                ColumnLayout {
                                                    Layout.fillWidth: true; Layout.preferredWidth: 1; spacing: 7
                                                    Text { text: "Decision"; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                                                    RowLayout {
                                                        Layout.fillWidth: true; spacing: 6
                                                        AppButton { label: root.editing ? "Save edit" : "Edit"; onClicked: { if (root.editing) { root.editing=false; root.setNotice("Edit staged in this prototype only.") } else { root.editedTitle=selectedCase.proposedTitle || ""; root.editedCredit=selectedCase.proposedArtists || ""; root.editing=true } } }
                                                        AppButton { label: "Reject"; onClicked: root.setNotice("Rejected decisions won't return on the next calculation.") }
                                                        AppButton { label: "Skip"; onClicked: root.setNotice("Skipped for now; no decision saved.") }
                                                        AppButton { label: "Unresolved"; onClicked: root.setNotice("Unresolved state recorded in the prototype.") }
                                                        AppButton { label: "Accept"; fill: Theme.primary; ink: Theme.textOnColor; accent: true; onClicked: root.setNotice("Accepted decision simulated. No tags or file names changed.") }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                Item {
                                    Column {
                                        anchors.centerIn: parent; width: Math.min(360, parent.width - 48); spacing: 11
                                        Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "search"; size: 28; color: Theme.textMuted }
                                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: "No matches"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 16; font.weight: Font.DemiBold }
                                        Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap; text: "Try another search or clear the filters. Your saved decisions are still here."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11 }
                                        AppButton { anchors.horizontalCenter: parent.horizontalCenter; label: "Clear search"; onClicked: { root.searchText=""; root.reviewState="ready" } }
                                    }
                                }

                                Item {
                                    Column {
                                        anchors.centerIn: parent; width: Math.min(460, parent.width - 48); spacing: 13
                                        Text { text: "Preparing proposals"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 17; font.weight: Font.DemiBold }
                                        Text { width: parent.width; text: "Reading the selected library records. Existing decisions are kept."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                        Rectangle { width: parent.width; height: 4; color: Theme.selection; Rectangle { width: parent.width * 0.62; height: parent.height; color: Theme.primary } }
                                        Text { text: "12 of 18 example files"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                                    }
                                }

                                Item {
                                    Column {
                                        anchors.centerIn: parent; width: Math.min(440, parent.width - 48); spacing: 12
                                        StateTag { label: "RECOVERABLE ERROR"; tint: Theme.danger }
                                        Text { text: "Could not compare this file"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 17; font.weight: Font.DemiBold }
                                        Text { width: parent.width; text: "The file may be unavailable or changed during review. Other proposals are ready."; color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11; wrapMode: Text.WordWrap }
                                        Row { spacing: 8; AppButton { label: "Retry this file"; fill: Theme.primary; ink: Theme.textOnColor; accent: true; onClicked: { root.reviewState="loading"; recalcTimer.restart() } } AppButton { label: "Skip for now"; onClicked: root.reviewState="ready" } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        visible: root.showNotice
        z: 70
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        width: Math.min(540, parent.width - 32)
        height: 42
        color: Theme.surface
        border.width: 1; border.color: Theme.separator
        Text { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; verticalAlignment: Text.AlignVCenter; text: root.noticeText; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight }
    }
    Timer { id: noticeTimer; interval: 2600; onTriggered: root.showNotice = false }
    Timer { id: recalcTimer; interval: 1700; onTriggered: root.reviewState = "ready" }

    Rectangle {
        visible: root.batchDialogOpen || root.aliasDialogOpen
        z: 100
        anchors.fill: parent
        color: "#B8000000"
        MouseArea { anchors.fill: parent; onClicked: { root.batchDialogOpen=false; root.aliasDialogOpen=false } }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(root.width - 36, root.aliasDialogOpen ? 480 : 540)
            height: root.aliasDialogOpen ? 264 : 318
            color: Theme.surface; border.width: 1; border.color: Theme.separator
            Column {
                anchors.fill: parent; anchors.margins: 22; spacing: 13
                Text { text: root.aliasDialogOpen ? "Link an alias?" : "Accept selected proposals?"; color: Theme.textPrimary; font.family: Theme.displayFontFamily; font.pixelSize: 18; font.weight: Font.Bold }
                Text {
                    width: parent.width; wrapMode: Text.WordWrap
                    text: root.aliasDialogOpen
                        ? "This explicitly links the displayed spelling to the selected artist. Similar names are never linked automatically."
                        : "This records " + root.batchSelection.length + " decisions in MTEE. It does not write audio tags or rename files."
                    color: Theme.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 11
                }
                Rectangle {
                    visible: !root.aliasDialogOpen
                    width: parent.width; height: 96; color: Theme.editor; border.width: 1; border.color: Theme.separator
                    Column { anchors.fill: parent; anchors.margins: 10; spacing: 6
                        Text { text: "Will be reviewed"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10; font.weight: Font.DemiBold }
                        Text { width: parent.width; text: "• " + root.batchSelection.length + " selected proposals\n• Proposed artist and title values\n• Existing rejected decisions stay rejected"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: 10; lineHeight: 1.15 }
                    }
                }
                Text { visible: !root.aliasDialogOpen; width: parent.width; wrapMode: Text.WordWrap; text: "A rejected proposal will not return on the next calculation. Unresolved items can be saved without blocking the rest of the batch."; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: 10 }
                Item { Layout.fillHeight: true }
                Row { spacing: 8; anchors.right: parent.right
                    AppButton { label: "Cancel"; onClicked: { root.batchDialogOpen=false; root.aliasDialogOpen=false } }
                    AppButton { label: root.aliasDialogOpen ? "Link alias in MTEE" : "Save decisions to MTEE"; fill: Theme.primary; ink: Theme.textOnColor; accent: true; onClicked: { root.batchDialogOpen=false; root.aliasDialogOpen=false; root.setNotice("Decision saved in this prototype only. Files remain unchanged.") } }
                }
            }
        }
    }
}
