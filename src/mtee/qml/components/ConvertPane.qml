import QtQuick
import Mtee

// Conversion batches of the session; the form itself is the Convert tab.
Item {
    id: pane

    required property var workspace

    objectName: "convertPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Convert"
    }

    Column {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 14

        TextButton {
            width: parent.width
            kind: "primary"
            icon: "plus"
            text: "New conversion"
            onClicked: pane.workspace.openConvert()
        }

        SectionLabel { text: "In progress" }

        Repeater {
            model: pane.workspace.convertBatches.filter((batch) => batch.state === "running")
            delegate: BatchRow {}
        }

        SectionLabel { text: "Recent" }

        Repeater {
            model: pane.workspace.convertBatches.filter((batch) => batch.state !== "running")
            delegate: BatchRow {}
        }
    }

    component BatchRow: Item {
        id: batch
        required property var modelData
        width: parent ? parent.width : 0
        height: 48

        Column {
            width: parent.width
            spacing: 4

            Text {
                width: parent.width
                text: batch.modelData.label
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Text {
                text: batch.modelData.detail
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
            ProgressLine {
                width: parent.width
                progress: batch.modelData.progress
                status: batch.modelData.state
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: pane.workspace.openConvert()
        }
    }
}
