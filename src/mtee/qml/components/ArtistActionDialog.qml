import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Rename, merge or delete one artist profile. Tracks already confirmed are counted
// and the optional change of the file tags is offered; nothing else is touched.
Dialog {
    id: dialog
    objectName: "artistActionDialog"

    required property var manager
    property string mode: "rename"
    property string artistId: ""
    property string artistName: ""
    property int confirmedTracks: 0
    property string destinationId: ""
    property bool alsoTags: false
    property string errorText: ""
    property var matches: []

    modal: true
    focus: true
    width: Math.min(500, parent ? parent.width - 48 : 500)
    anchors.centerIn: parent
    padding: 24
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.editor
        border.width: 1
        border.color: Theme.separator
    }

    readonly property string heading: mode === "rename" ? "Rename artist"
        : mode === "merge" ? "Merge into…" : "Delete artist"
    readonly property bool valid: mode === "delete"
        || (mode === "rename" && field.text.trim().length > 0)
        || (mode === "merge" && destinationId.length > 0)

    function show(action, id, name) {
        const impact = manager.artistImpact(id)
        mode = action
        artistId = id
        artistName = name
        confirmedTracks = impact.confirmedTracks || 0
        destinationId = ""
        alsoTags = false
        errorText = ""
        matches = []
        field.text = action === "rename" ? name : ""
        open()
        if (action !== "delete") {
            field.forceActiveFocus()
            field.selectAll()
        }
    }

    function apply() {
        let outcome
        if (mode === "rename")
            outcome = manager.renameArtist(artistId, field.text, alsoTags)
        else if (mode === "merge")
            outcome = manager.mergeArtist(artistId, destinationId, alsoTags)
        else
            outcome = manager.deleteArtist(artistId, alsoTags)
        if (outcome.ok)
            close()
        else
            errorText = outcome.error
    }

    contentItem: Column {
        spacing: 14

        Column {
            width: parent.width
            spacing: 2

            SectionLabel { text: "Artist" }

            Text {
                width: parent.width
                text: dialog.heading
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
            }

            Text {
                width: parent.width
                text: dialog.artistName
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }

        Item {
            visible: dialog.mode !== "delete"
            width: parent.width
            height: 36

            TextField {
                id: field
                objectName: "artistActionField"
                anchors.fill: parent
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                placeholderText: dialog.mode === "merge" ? "Search the artist to merge into" : "Name"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                background: Rectangle {
                    color: Theme.sidebar
                    border.color: field.activeFocus ? Theme.focus
                        : dialog.destinationId.length > 0 ? Theme.primary : Theme.separator
                }
                onTextEdited: {
                    if (dialog.mode !== "merge")
                        return
                    dialog.destinationId = ""
                    const found = dialog.manager.suggest(text)
                    dialog.matches = found.filter(entry => entry.id !== dialog.artistId)
                }
            }
        }

        Column {
            visible: dialog.mode === "merge" && dialog.destinationId.length === 0
                && dialog.matches.length > 0
            width: parent.width

            Repeater {
                model: dialog.matches.slice(0, 5)

                delegate: Rectangle {
                    id: match
                    required property var modelData
                    width: parent.width
                    height: 30
                    color: pick.containsMouse ? Theme.selection : Theme.surface

                    Text {
                        x: 10
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - 20
                        text: match.modelData.name
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    MouseArea {
                        id: pick
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            dialog.destinationId = match.modelData.id
                            field.text = match.modelData.name
                        }
                    }
                }
            }
        }

        Text {
            width: parent.width
            text: dialog.mode === "delete"
                ? "The artist is removed from the tracks it is credited on. No audio file is deleted. "
                    + "A track left without any artist goes back to Needs input."
                : dialog.mode === "merge"
                    ? "The two profiles become one. A track credited to both keeps a single credit."
                    : "The name changes everywhere; the identity of the artist stays the same."
            wrapMode: Text.Wrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            visible: dialog.confirmedTracks > 0
            width: parent.width
            text: dialog.confirmedTracks + " confirmed tracks are affected. Their files are renamed again with the new credit."
            wrapMode: Text.Wrap
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        CheckLine {
            visible: dialog.confirmedTracks > 0
            width: parent.width
            text: dialog.mode === "delete" ? "Also remove this artist from file tags" : "Also update file tags"
            checked: dialog.alsoTags
            onToggled: value => dialog.alsoTags = value
        }

        Text {
            visible: dialog.errorText.length > 0
            width: parent.width
            text: dialog.errorText
            wrapMode: Text.Wrap
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            width: parent.width
            spacing: 8
            layoutDirection: Qt.RightToLeft

            TextButton {
                objectName: "artistActionApply"
                text: dialog.mode === "delete" ? "Delete artist" : dialog.mode === "merge" ? "Merge" : "Rename"
                kind: dialog.mode === "delete" ? "secondary" : "primary"
                enabledAction: dialog.valid
                onClicked: dialog.apply()
            }

            TextButton {
                text: "Cancel"
                kind: "neutral"
                onClicked: dialog.close()
            }
        }
    }
}
