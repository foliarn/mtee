import QtQuick
import Mtee

// The artists of the selection as one chip each. A chip is one artist whatever its
// name holds, so "Nikita, the Wicked" is a single chip; a typed credit that would split
// asks first. Changes are staged and written by the panel's Save button, together with
// the artists catalog. With several tracks selected a chip shows how many name it.
Column {
    id: field

    required property var editor
    property bool editable: true
    property string reason: ""
    property string pending: ""
    readonly property var chips: field.editor.artistChips
    readonly property bool dirty: field.editor.dirtyFields.indexOf("artist") >= 0
    readonly property var matches: input.activeFocus && input.text.length > 0
        ? field.editor.artistSuggestions(input.text) : []

    spacing: 4

    function add(name) {
        field.editor.stageArtistAdd(name)
        input.text = ""
        field.pending = ""
    }

    function commit() {
        const text = input.text.trim()
        if (text.length === 0)
            return
        const parts = field.editor.splitPreview(text)
        if (parts.length > 1) {
            field.pending = text
            return
        }
        field.add(parts.length === 1 ? parts[0] : text)
    }

    Item {
        width: parent.width
        height: 20

        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Text {
                text: "Artist"
                color: field.dirty ? Theme.primary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Rectangle {
                visible: field.dirty
                anchors.verticalCenter: parent.verticalCenter
                width: 6
                height: 6
                radius: 3
                color: Theme.primary
            }

            Icon {
                visible: !field.editable
                anchors.verticalCenter: parent.verticalCenter
                name: "lock"
                size: 12
                color: Theme.textMuted

                MouseArea {
                    id: lockHover
                    anchors.fill: parent
                    anchors.margins: -4
                    hoverEnabled: true
                }

                HoverTip {
                    visible: lockHover.containsMouse && field.reason.length > 0
                    text: field.reason
                }
            }
        }

        IconButton {
            visible: field.dirty
            objectName: "revertArtists"
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 22
            height: 20
            icon: "undo"
            iconSize: 13
            tip: "Restore the original artists"
            onClicked: {
                field.pending = ""
                field.editor.revertField("artist")
            }
        }
    }

    Rectangle {
        width: parent.width
        height: box.implicitHeight + 12
        color: !field.editable ? Theme.sidebar : input.activeFocus ? Theme.editor : Theme.chrome
        border.width: 1
        border.color: input.activeFocus ? Theme.focus : field.dirty ? Theme.primary : Theme.separator

        Column {
            id: box
            x: 6
            y: 6
            width: parent.width - 12
            spacing: 6

            Flow {
                width: parent.width
                spacing: 6
                visible: field.chips.length > 0

                Repeater {
                    model: field.chips

                    delegate: Rectangle {
                        id: chip
                        objectName: "artistChip"
                        required property var modelData
                        readonly property bool partial: modelData.count < modelData.total

                        height: 24
                        width: Math.min(box.width, chipText.implicitWidth + (field.editable ? 38 : 20))
                        color: Theme.surface
                        border.width: 1
                        border.color: modelData.added ? Theme.primary : Theme.separator
                        opacity: chip.partial ? 0.8 : 1

                        Text {
                            id: chipText
                            x: 8
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, chip.width - (field.editable ? 38 : 20))
                            text: chip.modelData.name
                                + (chip.partial ? "  " + chip.modelData.count + "/" + chip.modelData.total : "")
                            elide: Text.ElideRight
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                            font.italic: chip.partial
                        }

                        IconButton {
                            visible: field.editable
                            objectName: "removeArtist"
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            width: 24
                            height: 24
                            icon: "close"
                            iconSize: 12
                            tip: "Remove this artist"
                            onClicked: field.editor.stageArtistRemove(chip.modelData.name)
                        }
                    }
                }
            }

            TextInput {
                id: input
                objectName: "artistInput"
                width: parent.width
                height: 24
                verticalAlignment: TextInput.AlignVCenter
                selectByMouse: true
                enabled: field.editable
                color: Theme.textPrimary
                selectionColor: Theme.primary
                selectedTextColor: Theme.textOnColor
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                clip: true
                onTextEdited: field.pending = ""
                onAccepted: field.commit()
                Keys.onEscapePressed: {
                    text = ""
                    field.pending = ""
                    focus = false
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: input.text.length === 0
                    text: field.chips.length === 0 ? "Add an artist" : "Add another artist"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }
    }

    Repeater {
        model: field.matches

        delegate: Rectangle {
            required property var modelData
            width: field.width
            height: 26
            color: matchMouse.containsMouse ? Theme.selection : Theme.surface

            Text {
                anchors.verticalCenter: parent.verticalCenter
                x: 10
                width: parent.width - 20
                text: parent.modelData.name
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            MouseArea {
                id: matchMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: (mouse) => {
                    field.add(parent.modelData.name)
                    mouse.accepted = true
                }
            }
        }
    }

    Column {
        width: parent.width
        spacing: 6
        visible: field.pending.length > 0

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: "“" + field.pending + "” holds a comma or &. Is it one artist or several?"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Flow {
            width: parent.width
            spacing: 6

            TextButton {
                objectName: "keepAsOneArtist"
                implicitHeight: 26
                kind: "neutral"
                text: "One artist"
                onClicked: field.add(field.pending)
            }

            TextButton {
                objectName: "splitArtists"
                implicitHeight: 26
                kind: "neutral"
                text: "Several artists"
                onClicked: {
                    const parts = field.editor.splitPreview(field.pending)
                    field.pending = ""
                    for (const part of parts)
                        field.editor.stageArtistAdd(part)
                    input.text = ""
                }
            }
        }
    }
}
