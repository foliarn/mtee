import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Confirmation of the lot frozen by the manager: how many tracks, how the files will
// be named, and the optional write of the tags. The tags box is off by default.
Dialog {
    id: dialog
    objectName: "artistConfirmDialog"

    required property var manager
    property var preview: ({ "items": [], "examples": [], "blocked": "", "trackCount": 0,
                             "artistCount": 0, "incompleteCount": 0, "scope": "tracks" })
    property bool writeTags: false
    readonly property bool byArtists: preview.scope === "artists"
    readonly property bool canConfirm: preview.blocked.length === 0 && preview.trackCount > 0
        && preview.incompleteCount === 0
    property string errorText: ""

    modal: true
    focus: true
    width: Math.min(560, parent ? parent.width - 48 : 560)
    anchors.centerIn: parent
    padding: 24
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.editor
        border.width: 1
        border.color: Theme.separator
    }

    function show(data) {
        preview = data
        writeTags = false
        errorText = ""
        open()
    }

    contentItem: Column {
        spacing: 14

        Column {
            width: parent.width
            spacing: 2

            SectionLabel { text: "Confirm" }

            Text {
                objectName: "artistConfirmTitle"
                width: parent.width
                text: dialog.byArtists
                    ? dialog.preview.artistCount + " artists · " + dialog.preview.trackCount + " tracks"
                    : "Confirm " + dialog.preview.trackCount + " tracks"
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
            }
        }

        Text {
            visible: dialog.preview.blocked.length > 0
            width: parent.width
            text: dialog.preview.blocked
            wrapMode: Text.Wrap
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            visible: dialog.preview.blocked.length === 0
            width: parent.width
            text: (dialog.byArtists
                ? "Every track of these artists is confirmed with its complete credit. "
                : "Only the tracks of the current filter are confirmed. ")
                + "Each file is renamed to “Artist, Artist - Title” and keeps its extension. "
                + "A name already in use gets a number."
            wrapMode: Text.Wrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Column {
            visible: dialog.preview.examples.length > 0 && dialog.preview.blocked.length === 0
            width: parent.width
            spacing: 6

            SectionLabel { text: "Examples" }

            Repeater {
                model: dialog.preview.examples

                delegate: Column {
                    id: example
                    required property var modelData
                    width: parent.width
                    spacing: 1

                    Text {
                        width: parent.width
                        text: example.modelData.from
                        elide: Text.ElideMiddle
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    Text {
                        width: parent.width
                        text: "→ " + example.modelData.to
                        elide: Text.ElideMiddle
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }
            }
        }

        Text {
            visible: dialog.preview.incompleteCount > 0
            width: parent.width
            text: dialog.preview.incompleteCount + " tracks still need an artist or a title. "
                + "Fix them with Edit, or move them to Needs input, then confirm again."
            wrapMode: Text.Wrap
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        CheckLine {
            objectName: "alsoUpdateTags"
            visible: dialog.preview.blocked.length === 0
            width: parent.width
            text: "Also update file tags"
            hint: "Writes the artists and the title into the tags. Other tags and covers are kept."
            checked: dialog.writeTags
            onToggled: value => dialog.writeTags = value
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
                objectName: "artistConfirmApply"
                text: dialog.byArtists ? "Confirm tracks" : "Confirm"
                kind: "primary"
                enabledAction: dialog.canConfirm
                onClicked: {
                    const label = dialog.byArtists
                        ? dialog.preview.artistCount + " artists"
                        : dialog.preview.trackCount + " tracks"
                    const outcome = dialog.manager.confirm(dialog.preview.items, dialog.writeTags, label)
                    if (outcome.ok)
                        dialog.close()
                    else
                        dialog.errorText = outcome.error
                }
            }

            TextButton {
                text: "Cancel"
                kind: "neutral"
                onClicked: dialog.close()
            }
        }
    }
}
