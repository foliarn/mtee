import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Correction of one track: title and one line per artist. Each line suggests the
// artists that already exist; typing a new name creates a profile when saved. Saving
// keeps a draft and never touches the file.
Dialog {
    id: dialog
    objectName: "artistEditDialog"

    required property var manager
    property string trackId: ""
    property string fileName: ""
    property string note: ""
    property string errorText: ""
    property var preview: ({ "name": "", "shortened": false, "collision": false })
    property bool moveToNeedsInput: false

    modal: true
    focus: true
    width: Math.min(580, parent ? parent.width - 48 : 580)
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

    function show(id) {
        const info = manager.editInfo(id)
        if (!info.trackId)
            return
        trackId = id
        fileName = info.filename
        note = info.note || ""
        errorText = ""
        titleField.text = info.title || ""
        lines.clear()
        for (const credit of info.credits)
            lines.append({ "lineId": credit.id, "lineName": credit.name })
        if (lines.count === 0)
            lines.append({ "lineId": "", "lineName": "" })
        refreshPreview()
        open()
        titleField.forceActiveFocus()
    }

    function entries() {
        const result = []
        for (let i = 0; i < lines.count; ++i) {
            const line = lines.get(i)
            if (line.lineName.trim().length > 0)
                result.push({ "id": line.lineId, "name": line.lineName })
        }
        return result
    }

    function refreshPreview() {
        const names = entries().map(entry => entry.name)
        preview = manager.previewName(trackId, names, titleField.text)
    }

    function save(toNeedsInput) {
        const outcome = manager.saveEdit(trackId, titleField.text, entries(), toNeedsInput)
        if (outcome.ok)
            close()
        else
            errorText = outcome.error
    }

    ListModel { id: lines }

    contentItem: Column {
        spacing: 14

        Column {
            width: parent.width
            spacing: 2

            SectionLabel { text: "Edit" }

            Text {
                width: parent.width
                text: dialog.fileName
                elide: Text.ElideMiddle
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
            }
        }

        Column {
            width: parent.width
            spacing: 4

            SectionLabel { text: "Title" }

            TextField {
                id: titleField
                objectName: "artistEditTitle"
                width: parent.width
                height: 36
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                placeholderText: "Title"
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                background: Rectangle {
                    color: Theme.sidebar
                    border.color: titleField.activeFocus ? Theme.focus : Theme.separator
                }
                onTextEdited: dialog.refreshPreview()
            }
        }

        Column {
            width: parent.width
            spacing: 4

            SectionLabel { text: "Artists" }

            Repeater {
                model: lines

                delegate: Item {
                    id: line
                    required property int index
                    required property string lineName
                    required property string lineId
                    property var matches: []

                    width: parent.width
                    height: 36

                    TextField {
                        id: field
                        objectName: "artistEditLine" + line.index
                        anchors.left: parent.left
                        anchors.right: removeButton.left
                        anchors.rightMargin: 6
                        height: 36
                        text: line.lineName
                        color: Theme.textPrimary
                        placeholderTextColor: Theme.textMuted
                        placeholderText: "Artist"
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                        background: Rectangle {
                            color: Theme.sidebar
                            border.color: field.activeFocus ? Theme.focus
                                : line.lineId.length > 0 ? Theme.primary : Theme.separator
                        }
                        onTextEdited: {
                            lines.setProperty(line.index, "lineName", text)
                            lines.setProperty(line.index, "lineId", "")
                            line.matches = text.trim().length > 0 ? dialog.manager.suggest(text) : []
                            suggestions.visible = line.matches.length > 0
                            dialog.refreshPreview()
                        }
                        onActiveFocusChanged: if (!activeFocus) closeTimer.restart()
                    }

                    Timer {
                        id: closeTimer
                        interval: 160
                        onTriggered: suggestions.visible = false
                    }

                    IconButton {
                        id: removeButton
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: 30
                        height: 30
                        icon: "close"
                        iconSize: 14
                        tip: "Remove this artist"
                        enabledAction: lines.count > 1
                        onClicked: {
                            lines.remove(line.index)
                            dialog.refreshPreview()
                        }
                    }

                    Rectangle {
                        id: suggestions
                        objectName: "artistSuggestions" + line.index
                        visible: false
                        z: 50
                        y: field.height + 2
                        width: field.width
                        height: Math.min(6, line.matches.length) * 30 + 2
                        color: Theme.surface
                        border.width: 1
                        border.color: Theme.separator

                        Column {
                            x: 1
                            y: 1
                            width: parent.width - 2

                            Repeater {
                                model: line.matches.slice(0, 6)

                                delegate: Rectangle {
                                    id: suggestion
                                    required property var modelData
                                    width: parent.width
                                    height: 30
                                    color: pick.containsMouse ? Theme.selection : "transparent"

                                    Text {
                                        x: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: parent.width - 20
                                        text: suggestion.modelData.name
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
                                            closeTimer.stop()
                                            lines.setProperty(line.index, "lineName", suggestion.modelData.name)
                                            lines.setProperty(line.index, "lineId", suggestion.modelData.id)
                                            suggestions.visible = false
                                            dialog.refreshPreview()
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            TextButton {
                objectName: "artistEditAddLine"
                text: "Add an artist"
                icon: "plus"
                kind: "ghost"
                onClicked: {
                    lines.append({ "lineId": "", "lineName": "" })
                    dialog.refreshPreview()
                }
            }
        }

        Column {
            width: parent.width
            spacing: 3

            SectionLabel { text: "File name after confirmation" }

            Text {
                objectName: "artistEditPreview"
                width: parent.width
                text: dialog.preview.name.length > 0 ? dialog.preview.name
                    : "Add an artist and a title to see the file name."
                elide: Text.ElideMiddle
                color: dialog.preview.name.length > 0 ? Theme.textPrimary : Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Text {
                visible: dialog.preview.shortened
                width: parent.width
                text: "The name is shortened to fit Windows limits. The title keeps its full text."
                wrapMode: Text.Wrap
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                visible: dialog.preview.collision
                width: parent.width
                text: "Another file already has this name: a number will be added."
                wrapMode: Text.Wrap
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                visible: dialog.note.length > 0
                width: parent.width
                text: dialog.note + " The tags are not replaced."
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
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

            TextButton {
                anchors.left: parent.left
                text: "Move to Needs input"
                kind: "ghost"
                tip: "Nothing usable was found for this track: fill it in later."
                onClicked: dialog.save(true)
            }

            Row {
                anchors.right: parent.right
                spacing: 8

                TextButton {
                    text: "Cancel"
                    kind: "neutral"
                    onClicked: dialog.close()
                }

                TextButton {
                    objectName: "artistEditSave"
                    text: "Save changes"
                    kind: "primary"
                    onClicked: dialog.save(false)
                }
            }
        }
    }
}
