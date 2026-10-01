import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Tag conflicts waiting for the user, then a compact view of the background jobs of
// this session: what runs now with its counter, and the last few that finished. The
// complete list, with times and failed items, is the Tasks page.
Item {
    id: pane

    required property var workspace
    readonly property var conflicts: workspace.tagConflicts
    readonly property bool hasConflictModel: conflicts && typeof conflicts.count === "number"
    readonly property int shownFinished: 3

    objectName: "tasksPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Tasks"
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

            TextButton {
                objectName: "openTasksPage"
                text: "Open Tasks page"
                kind: "ghost"
                width: parent.width
                onClicked: pane.workspace.openTasks()
            }

            Item {
                id: conflictsHeader
                objectName: "tagConflictsHeader"
                visible: conflictsRepeater.count > 0
                width: parent.width
                height: 24

                SectionLabel {
                    anchors.left: parent.left
                    anchors.right: conflictsHeaderButtons.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Tag conflicts (" + conflictsRepeater.count + ")"
                    elide: Text.ElideRight
                }

                Row {
                    id: conflictsHeaderButtons
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    IconButton {
                        objectName: "replaceAllConflicts"
                        width: 22
                        height: 22
                        icon: "check"
                        iconSize: 14
                        tip: "Replace all: delete the old tag values of every listed track and write the new ones"
                        onClicked: pane.conflicts.resolveAll()
                    }

                    IconButton {
                        objectName: "dismissAllConflicts"
                        width: 22
                        height: 22
                        icon: "close"
                        iconSize: 14
                        tip: "Dismiss all without writing"
                        onClicked: pane.conflicts.dismissAll()
                    }
                }
            }

            Repeater {
                id: conflictsRepeater
                model: pane.hasConflictModel ? pane.conflicts : null
                delegate: TaskConflictRow {
                    required property string trackId
                    required property string fileName
                    required property string summary
                    required property string conflictState
                    required property string errorMessage
                    width: content.width
                    title: fileName
                    detail: summary
                    stage: conflictState
                    error: errorMessage
                    onReplaceRequested: pane.conflicts.resolve(trackId)
                    onDismissRequested: pane.conflicts.dismiss(trackId)
                }
            }

            SectionLabel {
                visible: jobsRepeater.count > 0
                text: "This session"
            }

            Text {
                visible: jobsRepeater.count === 0
                width: parent.width
                text: "No background tasks in this session."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.WordWrap
            }

            Repeater {
                id: jobsRepeater
                model: jobsModel
                delegate: TaskRow {
                    required property string jobId
                    required property string label
                    required property string jobState
                    required property string stateLabel
                    required property real progress
                    required property int completed
                    required property int total
                    required property string detail
                    required property real elapsedSeconds
                    required property real remainingSeconds
                    required property string errorMessage
                    required property bool canCancel
                    required property int finishedRank

                    width: content.width
                    visible: finishedRank < 0 || finishedRank < pane.shownFinished
                    compact: true
                    onCancelRequested: jobsModel.cancel(jobId)
                }
            }

            Text {
                readonly property int hidden: jobsModel.finishedCount - pane.shownFinished
                visible: hidden > 0
                width: parent.width
                text: hidden + " more in the Tasks page"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
    }
}
