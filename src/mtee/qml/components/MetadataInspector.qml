import QtQuick
import Mtee

Panel {
    id: inspector

    property var workspace
    property bool compactMode: false
    property bool titleTouched: false
    property bool artistTouched: false
    property bool genreTouched: false
    property bool bpmTouched: false
    property bool keyTouched: false
    signal closeRequested()

    function commit(fieldName, value) {
        if (fieldName === "title") titleTouched = true
        if (fieldName === "artist") artistTouched = true
        if (fieldName === "genre") genreTouched = true
        if (fieldName === "bpm") bpmTouched = true
        if (fieldName === "key") keyTouched = true
        workspace.setSaveState("saving")
        saveTimer.restart()
    }

    Timer {
        id: saveTimer
        interval: 550
        onTriggered: workspace.setSaveState(workspace.scenarioName === "browser-multi" ? "error" : "saved")
    }

    SectionLabel {
        id: heading
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: close.left
        anchors.margins: Theme.spacing
        text: "Metadata"
    }

    ToolButton {
        id: close
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Theme.spacingSmall
        text: "Hide"
        onClicked: inspector.closeRequested()
    }

    Column {
        anchors.top: heading.bottom
        anchors.topMargin: Theme.spacing
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacing
        spacing: Theme.spacing

        Rectangle {
            width: parent.width
            height: Math.min(parent.width * 0.58, 170)
            radius: Theme.controlRadius
            color: Theme.activeSurface

            Text {
                anchors.centerIn: parent
                text: workspace.noArtwork ? "No artwork" : "Artwork preview"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Text {
            width: parent.width
            text: workspace.selectedRows.length > 1 ? workspace.selectedRows.length + " tracks selected" : "1 track selected"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Flickable {
            width: parent.width
            height: Math.max(0, parent.height - 235)
            contentHeight: fields.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: fields
                width: parent.width
                spacing: Theme.spacing

                FieldEditor {
                    width: fields.width
                    label: "Title"
                    value: workspace.selectedRows.length > 1 ? "" : "Carrier Wave"
                    mixed: workspace.multiSelection && !inspector.titleTouched
                    onCommitted: (value) => inspector.commit("title", value)
                }
                FieldEditor {
                    width: fields.width
                    label: "Artist"
                    value: workspace.selectedRows.length > 1 ? "" : "Loop Foundry"
                    mixed: workspace.multiSelection && !inspector.artistTouched
                    onCommitted: (value) => inspector.commit("artist", value)
                }
                FieldEditor {
                    width: fields.width
                    label: "Genre"
                    value: workspace.selectedRows.length > 1 ? "" : "Techno"
                    mixed: workspace.multiSelection && !inspector.genreTouched
                    onCommitted: (value) => inspector.commit("genre", value)
                }
                FieldEditor {
                    width: fields.width
                    label: "BPM"
                    value: workspace.selectedRows.length > 1 ? "" : "134"
                    mixed: workspace.multiSelection && !inspector.bpmTouched
                    onCommitted: (value) => inspector.commit("bpm", value)
                }
                FieldEditor {
                    width: fields.width
                    label: "Key"
                    value: workspace.selectedRows.length > 1 ? "" : "5A"
                    mixed: workspace.multiSelection && !inspector.keyTouched
                    onCommitted: (value) => inspector.commit("key", value)
                }
            }
        }

        Row {
            spacing: Theme.spacingSmall

            Text {
                text: workspace.saveState === "saving" ? "Saving…"
                    : workspace.saveState === "saved" ? "Saved"
                    : workspace.saveState === "error" ? "Could not save"
                    : "Changes save when you leave a field"
                color: workspace.saveState === "error" ? Theme.danger : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                verticalAlignment: Text.AlignVCenter
            }

            ToolButton {
                visible: workspace.saveState === "error"
                text: "Retry"
                onClicked: {
                    workspace.setSaveState("saving")
                    saveTimer.restart()
                }
            }

            ToolButton {
                visible: workspace.saveState === "saved" || workspace.saveState === "error"
                text: "Undo"
                onClicked: workspace.setSaveState("idle")
            }
        }
    }
}
