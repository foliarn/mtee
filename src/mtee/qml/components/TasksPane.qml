import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Background tasks: invented examples plus the real jobs of the session.
Item {
    id: pane

    required property var workspace

    objectName: "tasksPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Tasks"

        IconButton {
            icon: "plus"
            iconSize: 16
            width: 26
            height: 26
            tip: "Run sample task"
            onClicked: shell.startSampleJob()
        }
    }

    Flickable {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        contentHeight: content.implicitHeight + 16
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: content
            x: 16
            width: parent.width - 32
            spacing: 14

            Repeater {
                model: pane.workspace.tasks
                delegate: TaskRow {
                    label: modelData.label
                    detail: modelData.detail
                    status: modelData.state
                    progress: modelData.progress
                }
            }

            SectionLabel {
                visible: jobsRepeater.count > 0
                text: "This session"
            }

            Repeater {
                id: jobsRepeater
                model: jobsModel
                delegate: TaskRow {
                    required label
                    required progress
                    required property string stateLabel
                    required property string jobState
                    required property string errorMessage
                    detail: errorMessage.length > 0 ? errorMessage : stateLabel
                    status: jobState === "failed" ? "error"
                        : jobState === "running" || jobState === "queued" ? "running" : "done"
                }
            }
        }
    }

    component TaskRow: Column {
        id: taskRow

        property string label: ""
        property string detail: ""
        property string status: "running"
        property real progress: 0

        width: content.width
        spacing: 4

        Row {
            width: parent.width
            spacing: 6

            Icon {
                visible: taskRow.status === "error"
                name: "alert"
                size: 14
                color: Theme.danger
                anchors.verticalCenter: parent.verticalCenter
            }

            Text {
                width: parent.width - 20
                text: taskRow.label
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }

        Text {
            width: parent.width
            text: taskRow.detail
            wrapMode: Text.WordWrap
            color: taskRow.status === "error" ? Theme.danger : Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        ProgressLine {
            width: parent.width
            progress: taskRow.progress
            status: taskRow.status
        }
    }
}
