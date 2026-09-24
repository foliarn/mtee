import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

Dialog {
    id: dialog

    required property var operations

    modal: true
    focus: true
    width: 760
    height: 660
    anchors.centerIn: parent
    title: operations.kind === "rename" ? "Rename audio file"
        : operations.kind === "move" ? "Move audio files"
        : "Move to trash"
    standardButtons: Dialog.NoButton

    background: Rectangle {
        color: Theme.editor
        border.width: 1
        border.color: Theme.separator
    }

    FolderDialog {
        id: destinationPicker
        title: "Choose a destination folder"
        onAccepted: {
            targetField.text = selectedFolder.toString()
            dialog.operations.setPreviewTarget(targetField.text)
        }
    }

    contentItem: Column {
        spacing: 12

        Text {
            text: dialog.operations.kind === "rename"
                ? "The audio extension is kept. MTEE checks the destination again before moving the file."
                : dialog.operations.kind === "move"
                    ? "Moves stay inside a registered library root. Cross-volume copies are verified before the source is removed; existing files are never replaced."
                    : "Move to trash is disabled until Windows recycle and restore behavior passes native validation."
            wrapMode: Text.Wrap
            color: dialog.operations.kind === "trash" ? Theme.danger : Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            width: parent.width
            spacing: 8
            visible: dialog.operations.kind === "rename" || dialog.operations.kind === "move"

            TextField {
                id: targetField
                width: parent.width - (chooseFolder.visible ? chooseFolder.implicitWidth + parent.spacing : 0)
                placeholderText: dialog.operations.kind === "rename"
                    ? "New file name" : "Destination folder path"
                text: dialog.operations.previewTarget
                selectByMouse: true
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                onTextEdited: dialog.operations.setPreviewTarget(text)
                background: Rectangle {
                    color: Theme.surface
                    border.width: 1
                    border.color: targetField.activeFocus ? Theme.focus : Theme.separator
                }
            }

            TextButton {
                id: chooseFolder
                visible: dialog.operations.kind === "move"
                kind: "neutral"
                text: "Choose…"
                enabledAction: dialog.operations.state !== "running"
                onClicked: destinationPicker.open()
            }
        }

        Text {
            text: dialog.operations.kind === "rename" ? "Preview" : "Files and destinations"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            font.weight: Font.DemiBold
        }

        ProgressLine {
            width: parent.width
            visible: dialog.operations.state === "running"
            progress: dialog.operations.progress
            status: "running"
        }

        Rectangle {
            width: parent.width
            height: 210
            color: Theme.sidebar
            border.width: 1
            border.color: Theme.separator

            ListView {
                anchors.fill: parent
                anchors.margins: 1
                clip: true
                model: dialog.operations.previewTargets
                ScrollBar.vertical: ScrollBar {}

                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 76
                    color: modelData.status === "ready" ? "transparent" : Theme.surface

                    Column {
                        anchors.fill: parent
                        anchors.margins: 9
                        spacing: 3
                        Text {
                            width: parent.width
                            text: modelData.source
                            elide: Text.ElideMiddle
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                        Text {
                            width: parent.width
                            text: modelData.status === "ready"
                                ? "→  " + modelData.destination
                                : modelData.message
                            elide: Text.ElideMiddle
                            color: modelData.status === "ready" ? Theme.textPrimary : Theme.danger
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: 1
                        color: Theme.separator
                    }
                }
            }
        }

        Text {
            width: parent.width
            visible: dialog.operations.message.length > 0
            text: dialog.operations.message
            wrapMode: Text.Wrap
            color: dialog.operations.state === "recovery" ? Theme.danger : Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Rectangle {
            width: parent.width
            height: 72
            visible: dialog.operations.results.length > 0
            color: Theme.sidebar
            border.width: 1
            border.color: Theme.separator

            ListView {
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                model: dialog.operations.results
                ScrollBar.vertical: ScrollBar {}
                delegate: Text {
                    required property var modelData
                    width: ListView.view.width
                    height: 38
                    text: modelData.status.toUpperCase() + "  " + modelData.source
                        + (modelData.destination ? "  →  " + modelData.destination : "")
                    elide: Text.ElideMiddle
                    color: modelData.status === "completed" ? Theme.primary
                        : modelData.status === "recovery" ? Theme.danger : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Rectangle {
            width: parent.width
            height: dialog.operations.recoveryOperations.length > 0 ? 118 : 0
            visible: dialog.operations.recoveryOperations.length > 0
            color: Theme.surface
            border.width: 1
            border.color: Theme.danger

            Column {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 6
                Text {
                    text: "File operations need inspection"
                    color: Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    font.weight: Font.DemiBold
                }

                ListView {
                    width: parent.width
                    height: parent.height - 30
                    clip: true
                    model: dialog.operations.recoveryOperations
                    delegate: Item {
                        required property var modelData
                        width: ListView.view.width
                        height: 42

                        Text {
                            anchors.left: parent.left
                            anchors.right: completeRecovery.left
                            anchors.rightMargin: completeRecovery.visible ? 8 : 0
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.situation + ": " + modelData.source + " → "
                                + (modelData.recoveryPath || modelData.destination)
                            elide: Text.ElideMiddle
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeCaption
                        }

                        TextButton {
                            id: completeRecovery
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            visible: modelData.canCompleteDestination
                            kind: "neutral"
                            text: "Use verified destination"
                            enabledAction: dialog.operations.state !== "running"
                            tip: "Recheck the file and update the track location without replacing either path."
                            onClicked: dialog.operations.completeRecoveryToDestination(
                                modelData.operationId
                            )
                        }
                    }
                }
            }
        }

        Item { width: 1; height: 1 }

        Row {
            width: parent.width
            spacing: 8

            TextButton {
                visible: dialog.operations.canUndo
                kind: "ghost"
                text: "Undo last move"
                enabledAction: dialog.operations.state !== "running"
                onClicked: dialog.operations.undo()
            }

            TextButton {
                visible: dialog.operations.canStopPlaybackAndContinue
                kind: "neutral"
                text: "Stop playback and continue"
                onClicked: dialog.operations.stopPlaybackAndContinue()
            }

            TextButton {
                visible: dialog.operations.canCancel
                kind: "ghost"
                text: "Cancel"
                onClicked: dialog.operations.cancel()
            }

            TextButton {
                visible: dialog.operations.state === "result" && !dialog.operations.canStopPlaybackAndContinue
                    && dialog.operations.results.some(item => item.status === "busy")
                kind: "neutral"
                text: "Retry busy file"
                onClicked: dialog.operations.retryBusy()
            }

            TextButton {
                kind: "ghost"
                text: "Close"
                onClicked: dialog.close()
            }

            TextButton {
                visible: dialog.operations.state === "preview"
                kind: "primary"
                text: dialog.operations.kind === "rename" ? "Rename"
                    : dialog.operations.kind === "move" ? "Move" : "Unavailable"
                enabledAction: dialog.operations.canExecute
                onClicked: dialog.operations.execute()
            }
        }
    }
}
