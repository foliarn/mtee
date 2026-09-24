import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Tags of the selection (editable) and technical details (read-only), with the
// save status of the last change at the bottom.
Item {
    id: info

    required property var workspace
    readonly property var selection: workspace.selectedIds
    readonly property var first: (workspace.revision, selection.length > 0 ? workspace.track(selection[0]) : ({}))
    readonly property bool multiple: selection.length > 1

    objectName: "infoPanel"

    Timer {
        interval: 550
        running: info.workspace.saveState === "saving"
        onTriggered: info.workspace.finishSave()
    }

    Text {
        visible: info.selection.length === 0
        anchors.centerIn: parent
        width: parent.width - 48
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        text: "Select a track to see its info."
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    Flickable {
        id: scroller
        visible: info.selection.length > 0
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: footer.top
        contentHeight: body.implicitHeight + 24
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: body
            x: 16
            y: 16
            width: scroller.width - 32
            spacing: 16

            Row {
                width: parent.width
                spacing: 12

                Item {
                    width: 64
                    height: 64

                    CoverArt {
                        visible: info.multiple
                        x: 8
                        width: 56
                        height: 56
                        pattern: info.selection.length > 1 ? info.workspace.track(info.selection[1]).cover : -1
                        opacity: 0.6
                    }

                    CoverArt {
                        y: info.multiple ? 8 : 0
                        width: info.multiple ? 56 : 64
                        height: width
                        pattern: info.first.cover !== undefined ? info.first.cover : -1
                    }
                }

                Column {
                    width: parent.width - 76
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        width: parent.width
                        text: info.multiple ? info.selection.length + " tracks selected" : (info.first.title || "")
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeTitle
                        font.weight: Font.Bold
                    }

                    Text {
                        width: parent.width
                        text: info.multiple ? "Changes apply to every selected track"
                            : (info.first.artist && info.first.artist.length > 0 ? info.first.artist : "Unknown artist")
                        wrapMode: Text.Wrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }
            }

            SectionLabel { text: "Tags" }

            Repeater {
                model: info.workspace.infoFields
                delegate: FieldEditor {
                    required property var modelData
                    width: body.width
                    label: modelData.label
                    value: modelData.value
                    mixed: modelData.mixed
                    onCommitted: (value) => info.workspace.commitField(modelData.key, value)
                }
            }

            SectionLabel {
                visible: !info.multiple
                text: "File"
            }

            Repeater {
                model: info.workspace.infoFile
                delegate: Column {
                    required property var modelData
                    width: body.width
                    spacing: 2

                    Text {
                        text: modelData.label
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    Text {
                        width: parent.width
                        text: modelData.value
                        wrapMode: Text.WrapAnywhere
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }
            }
        }
    }

    Rectangle {
        id: footer
        visible: info.selection.length > 0
        anchors.bottom: parent.bottom
        width: parent.width
        height: 48
        color: Theme.sidebar

        Rectangle {
            width: parent.width
            height: 1
            color: Theme.separator
        }

        Row {
            x: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            Icon {
                anchors.verticalCenter: parent.verticalCenter
                visible: info.workspace.saveState === "saved" || info.workspace.saveState === "error"
                name: info.workspace.saveState === "error" ? "alert" : "check"
                size: 16
                color: info.workspace.saveState === "error" ? Theme.danger : Theme.primary
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: info.workspace.saveState === "saving" ? "Saving…"
                    : info.workspace.saveState === "saved" ? "Saved"
                    : info.workspace.saveState === "error" ? "Could not save"
                    : "Changes save when you leave a field"
                color: info.workspace.saveState === "error" ? Theme.danger
                    : info.workspace.saveState === "idle" ? Theme.textMuted : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            TextButton {
                visible: info.workspace.saveState === "error"
                implicitHeight: 28
                kind: "neutral"
                text: "Retry"
                onClicked: info.workspace.retrySave()
            }

            TextButton {
                visible: info.workspace.saveState === "saved" || info.workspace.saveState === "error"
                implicitHeight: 28
                kind: "ghost"
                text: "Undo"
                onClicked: info.workspace.undoSave()
            }
        }
    }
}
