import QtQuick
import QtQuick.Controls.Basic
import Mtee

Dialog {
    id: dialog
    objectName: "trashDialog"

    required property var trashModel

    modal: true
    focus: true
    width: 620
    // Plugin choices (plan 125.4) make the dialog taller; the file list gives some room back.
    // Without a plugin choice the height is the 510 px it always was.
    readonly property real windowHeight: parent && parent.Window.window ? parent.Window.window.height : 900
    height: Math.max(510, Math.min(510 + (choiceBlock.visible ? Math.max(0, choiceBlock.height + 12 - 110) : 0),
                                   windowHeight - 40))
    // Like the other dialogs of the core: centred over the window. Loaded inside Main.qml's
    // Loader, which is 0 x 0 at the top-left corner, it would otherwise centre on that corner.
    parent: Overlay.overlay
    anchors.centerIn: parent
    title: trashModel.state === "confirm"
        ? (trashModel.folderSummary.length > 0 ? "Move folder to Recycle Bin"
            : trashModel.hasLocalFiles ? "Move to Recycle Bin" : "Choose an action")
        : "Recycle operation"
    standardButtons: Dialog.NoButton

    background: Rectangle {
        radius: Theme.radiusWindow
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
                    ? (dialog.trashModel.folderSummary.length > 0
                        ? dialog.trashModel.folderSummary + " Move it to the Windows Recycle Bin?"
                    : dialog.trashModel.hasLocalFiles
                        ? "Move " + dialog.trashModel.selectedCount + " selected audio file(s) to the Windows Recycle Bin?"
                        : "None of the selected tracks has a file on this computer, so none can go to the Windows Recycle Bin.")
                    : dialog.trashModel.message
            wrapMode: Text.Wrap
            color: dialog.trashModel.state === "result" ? Theme.textSecondary : Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            visible: dialog.trashModel.state === "confirm" && dialog.trashModel.hasLocalFiles
            text: "You can restore recycled files from the Windows Recycle Bin. If a file is in use, stop playback and retry it."
            wrapMode: Text.Wrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Rectangle {
            width: parent.width
            height: choiceBlock.visible ? 140 : 250
            color: Theme.sidebar
            border.width: 1
            border.color: Theme.separator

            ListView {
                id: resultsList
                WheelScrollHandler { flickable: resultsList }
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

        // What plugins offer for this selection, one group per plugin under its name. Approved
        // 2026-11-02 (private/docs/ux/review-125-126.md, Decision 3), see TrashModel.
        Column {
            id: choiceBlock
            objectName: "trashChoices"
            width: parent.width
            spacing: 8
            visible: dialog.trashModel.state === "confirm"
                && (dialog.trashModel.choiceGroups || []).length > 0

            Repeater {
                model: dialog.trashModel.choiceGroups

                delegate: Column {
                    id: choiceGroup
                    required property var modelData
                    width: choiceBlock.width
                    spacing: 6

                    SectionLabel {
                        objectName: "trashChoiceHeading"
                        text: choiceGroup.modelData.plugin
                    }

                    Repeater {
                        model: choiceGroup.modelData.choices

                        delegate: Rectangle {
                            id: choiceCard
                            required property var modelData
                            objectName: "trashChoiceCard"
                            width: choiceGroup.width
                            height: cardText.implicitHeight + 16
                            color: Theme.surface

                            Rectangle {
                                width: 3
                                height: parent.height
                                color: choiceCard.modelData.tone === "danger" ? Theme.danger : Theme.primary
                            }

                            Column {
                                id: cardText
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.leftMargin: 14
                                anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 2

                                Text {
                                    width: parent.width
                                    text: choiceCard.modelData.label
                                    wrapMode: Text.Wrap
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSecondary
                                    font.weight: Font.DemiBold
                                }

                                Text {
                                    width: parent.width
                                    visible: text.length > 0
                                    text: choiceCard.modelData.description
                                    wrapMode: Text.Wrap
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeCaption
                                }
                            }
                        }
                    }
                }
            }
        }

        // A Flow, not a Row: with several plugin choices the buttons wrap instead of overflowing.
        Flow {
            width: parent.width
            spacing: 8
            layoutDirection: Qt.RightToLeft

            TextButton {
                // A plugin choice that replaces the core action takes this button's place.
                visible: !dialog.trashModel.replacesRecycle
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

            // The plugin choices, the default first (rightmost). Danger buttons come after the
            // others, so the destructive choice is farthest from the default one.
            Repeater {
                model: dialog.trashModel.choiceButtons

                delegate: TextButton {
                    required property var modelData
                    objectName: "trashChoice_" + modelData.key
                    visible: modelData.kind !== "danger"
                    text: modelData.label
                    kind: modelData.kind
                    onClicked: dialog.trashModel.run_choice(modelData.key)
                }
            }

            Repeater {
                model: dialog.trashModel.choiceButtons

                delegate: DangerButton {
                    required property var modelData
                    objectName: "trashChoice_" + modelData.key
                    visible: modelData.kind === "danger"
                    text: modelData.label
                    onClicked: dialog.trashModel.run_choice(modelData.key)
                }
            }

            // Closes the confirmation without doing anything: the same as Escape (reject).
            TextButton {
                objectName: "trashCancel"
                visible: dialog.trashModel.state === "confirm"
                text: "Cancel"
                kind: "ghost"
                onClicked: dialog.reject()
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
