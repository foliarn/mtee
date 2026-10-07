import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Types, Bass-related flag, hidden state (idgaf) and free tags of one artist. Saving
// only writes the artists database; no audio file is touched.
Dialog {
    id: dialog
    objectName: "artistProfileDialog"

    required property var manager
    readonly property var allRoles: ["Producer", "DJ", "Singer", "MC"]
    property string artistId: ""
    property string artistName: ""
    property var roles: []
    property int bass: -1
    property bool hidden: false
    property string errorText: ""

    modal: true
    focus: true
    width: Math.min(480, parent ? parent.width - 48 : 480)
    anchors.centerIn: parent
    padding: 24
    title: ""
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape

    background: Rectangle {
        color: Theme.editor
        border.width: 1
        border.color: Theme.separator
    }

    function show(id, name) {
        const profile = manager.artistProfile(id)
        artistId = id
        artistName = name
        roles = profile.roles
        bass = profile.bassRelated === null || profile.bassRelated === undefined ? -1 : (profile.bassRelated ? 1 : 0)
        hidden = profile.hidden
        tagsField.text = profile.tags.join(", ")
        errorText = ""
        open()
        tagsField.forceActiveFocus()
    }

    function toggleRole(role) {
        roles = roles.indexOf(role) >= 0 ? roles.filter(item => item !== role) : roles.concat([role])
    }

    function save() {
        const tags = tagsField.text.split(",").map(tag => tag.trim()).filter(tag => tag.length > 0)
        const outcome = manager.saveArtistProfile(artistId, roles, bass, tags, hidden)
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

            SectionLabel { text: "Artist profile" }

            Text {
                width: parent.width
                text: dialog.artistName
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
            }
        }

        Column {
            width: parent.width
            spacing: 6

            SectionLabel { text: "Types" }

            Row {
                spacing: 6

                Repeater {
                    model: dialog.allRoles

                    delegate: FilterChip {
                        required property string modelData
                        objectName: "profileRole" + modelData
                        text: modelData
                        checked: dialog.roles.indexOf(modelData) >= 0
                        onToggled: dialog.toggleRole(modelData)
                    }
                }
            }
        }

        Column {
            width: parent.width
            spacing: 6

            SectionLabel { text: "Bass-related" }

            Row {
                spacing: 6

                Repeater {
                    model: [{ "label": "Unknown", "value": -1 }, { "label": "Yes", "value": 1 }, { "label": "No", "value": 0 }]

                    delegate: FilterChip {
                        required property var modelData
                        objectName: "profileBass" + modelData.label
                        text: modelData.label
                        checked: dialog.bass === modelData.value
                        onToggled: dialog.bass = modelData.value
                    }
                }
            }
        }

        Row {
            width: parent.width
            spacing: 10

            ToggleSwitch {
                id: hiddenSwitch
                objectName: "profileHidden"
                anchors.verticalCenter: parent.verticalCenter
                checked: dialog.hidden
                onToggled: (value) => dialog.hidden = value
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - hiddenSwitch.width - 10
                text: "idgaf — hide this artist from the lists"
                wrapMode: Text.Wrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }

        Column {
            width: parent.width
            spacing: 4

            SectionLabel { text: "Tags" }

            TextField {
                id: tagsField
                objectName: "profileTags"
                width: parent.width
                height: 36
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                placeholderText: "Separated by commas"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                selectByMouse: true
                background: Rectangle {
                    color: Theme.sidebar
                    border.color: tagsField.activeFocus ? Theme.focus : Theme.separator
                }
                onAccepted: dialog.save()
            }
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

        Item {
            width: parent.width
            height: 32

            Row {
                anchors.right: parent.right
                spacing: 8

                TextButton {
                    text: "Cancel"
                    kind: "neutral"
                    onClicked: dialog.close()
                }

                TextButton {
                    objectName: "profileSave"
                    text: "Save"
                    kind: "primary"
                    onClicked: dialog.save()
                }
            }
        }
    }
}
