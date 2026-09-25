import QtQuick
import QtQuick.Controls.Basic
import Mtee

Dialog {
    id: dialog

    required property var trashModel

    modal: true
    focus: true
    width: 620
    height: 510
    anchors.centerIn: parent
    title: trashModel.state === "confirm" ? "Move to Recycle Bin" : "Recycle operation"
    standardButtons: Dialog.NoButton

    background: Rectangle {
        color: Theme.editor
        border.width: 1
        border.color: Theme.separator
    }

    onRejected: {
        if (trashModel.canCancel)
            trashModel.cancel()
    }

    Connections {
        target: dialog.trashModel
        function onDialogRequested() { dialog.open() }
    }

    contentItem: Column {
        spacing: 12

        Text {
            width: parent.width
            text: dialog.trashModel.state === "preparing"
                ? dialog.trashModel.message
                : dialog.trashModel.state === "confirm"
                    ? "Move " + dialog.trashModel.selectedCount + " selected audio file(s) to the Windows Recycle Bin?"
                    : dialog.trashModel.message
            wrapMode: Text.Wrap
            color: dialog.trashModel.state === "result" ? Theme.textSecondary : Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            visible: dialog.trashModel.state === "confirm"
            text: "You can restore recycled files from the Windows Recycle Bin. If a file is in use, stop playback and retry it."
            wrapMode: Text.Wrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Rectangle {
            width: parent.width
            height: 250
            color: Theme.sidebar
            border.width: 1
            border.color: Theme.separator

            ListView {
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                model: dialog.trashModel.results
                ScrollBar.vertical: ScrollBar {}

                delegate: Item {
                    id: resultRow
                    required property var modelData
                    width: ListView.view.width
                    height: 58

                    Column {
                        anchors.fill: parent
                        spacing: 3

                        Text {
                            width: parent.width
                            text: resultRow.modelData.status.toUpperCase() + "  " + resultRow.modelData.source
                            elide: Text.ElideMiddle
                            color: resultRow.modelData.status === "recycled" ? Theme.primary : Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        Text {
                            width: parent.width
                            text: resultRow.modelData.message
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeCaption
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

        Row {
            width: parent.width
            spacing: 8
            layoutDirection: Qt.RightToLeft

            TextButton {
                text: dialog.trashModel.state === "confirm" ? "Move to Recycle Bin" : "Close"
                kind: dialog.trashModel.state === "confirm" ? "primary" : "neutral"
                enabledAction: dialog.trashModel.state === "confirm" || dialog.trashModel.state === "result"
                onClicked: {
                    if (dialog.trashModel.state === "confirm")
                        dialog.trashModel.confirm()
                    else
                        dialog.close()
                }
            }

            TextButton {
                visible: dialog.trashModel.canStopPlaybackAndContinue
                text: "Stop playback and retry"
                kind: "secondary"
                onClicked: dialog.trashModel.stop_playback_and_continue()
            }

            TextButton {
                visible: dialog.trashModel.state === "result" && dialog.trashModel.hasBusyFiles
                text: "Retry in-use files"
                onClicked: dialog.trashModel.retry_busy()
            }

            TextButton {
                visible: dialog.trashModel.canCancel
                text: "Cancel"
                kind: "ghost"
                onClicked: dialog.trashModel.cancel()
            }
        }
    }
}
