import QtQuick
import Mtee

// Background tasks of the session: label, state and progress, with a
// cancellation for the task that is still active.
Item {
    id: strip

    property alias model: list.model
    signal cancelRequested(string jobId)

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        spacing: Theme.spacingSmall
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true

        delegate: Item {
            id: entry
            required property string jobId
            required property string label
            required property string jobState
            required property string stateLabel
            required property real progress
            required property string errorMessage

            width: list.width
            height: 44

            readonly property bool active: jobState === "queued" || jobState === "running"

            Text {
                id: name
                anchors.top: parent.top
                anchors.left: parent.left
                text: entry.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                anchors.top: parent.top
                anchors.right: cancel.left
                anchors.rightMargin: Theme.spacing
                text: entry.stateLabel
                color: entry.jobState === "failed" ? Theme.danger : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            ToolButton {
                id: cancel
                anchors.top: parent.top
                anchors.right: parent.right
                text: "Cancel"
                enabledAction: entry.active
                onClicked: strip.cancelRequested(entry.jobId)
            }

            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottomMargin: Theme.spacingSmall
                height: 4
                radius: 2
                color: Theme.activeSurface

                Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, entry.progress))
                    height: parent.height
                    radius: parent.radius
                    color: entry.jobState === "failed" ? Theme.danger : Theme.accent
                }
            }
        }
    }

    Text {
        anchors.centerIn: parent
        visible: list.count === 0
        text: "No background task yet"
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }
}
