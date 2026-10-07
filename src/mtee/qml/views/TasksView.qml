import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../components"

// Tasks page: every background job of this session with its counter, current item,
// time spent and left, cancellation and the items that failed, plus the tag
// conflicts waiting for the user. The sidebar keeps a compact summary.
Rectangle {
    id: page

    required property var workspace
    property int bottomInset: 0
    readonly property var conflicts: workspace.tagConflicts
    readonly property bool hasConflictModel: conflicts && typeof conflicts.count === "number"
    readonly property int active: jobsModel.activeCount
    readonly property int finished: jobsModel.finishedCount
    readonly property string summary: {
        const parts = []
        const running = jobsModel.runningCount
        if (running > 0)
            parts.push(running + " running")
        if (page.active - running > 0)
            parts.push((page.active - running) + " queued")
        if (page.finished > 0)
            parts.push(page.finished + " finished")
        return parts.length > 0 ? parts.join(" · ") : "Nothing is running"
    }

    objectName: "tasksView"
    color: Theme.editor

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.bottomMargin: page.bottomInset
        contentHeight: column.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: column
            x: Math.max(24, (scroller.width - width) / 2)
            width: Math.min(900, scroller.width - 48)
            spacing: 18

            // Heading placed like the folder page, at the page padding rather than
            // inside the centred content column; the summary sits under the title.
            Item {
                readonly property int pagePadding: scroller.width < 600 ? 12 : 24

                x: pagePadding - column.x
                width: scroller.width - 2 * pagePadding
                height: 92

                Column {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 14
                    spacing: 2

                    SectionLabel { text: "Tasks" }

                    Text {
                        text: "Background tasks"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeHeading
                        font.weight: Font.Bold
                    }

                    Text {
                        objectName: "tasksSummary"
                        text: page.summary
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }

                TextButton {
                    objectName: "clearFinishedTasks"
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 14
                    text: "Clear finished"
                    kind: "ghost"
                    enabledAction: page.finished > 0
                    onClicked: jobsModel.clearFinished()
                }
            }

            Item {
                visible: conflictsRepeater.count > 0
                width: parent.width
                height: 24

                SectionLabel {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Tag conflicts (" + conflictsRepeater.count + ")"
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    IconButton {
                        width: 22
                        height: 22
                        icon: "check"
                        iconSize: 14
                        tip: "Replace all: delete the old tag values of every listed track and write the new ones"
                        onClicked: page.conflicts.resolveAll()
                    }

                    IconButton {
                        width: 22
                        height: 22
                        icon: "close"
                        iconSize: 14
                        tip: "Dismiss all without writing"
                        onClicked: page.conflicts.dismissAll()
                    }
                }
            }

            Repeater {
                id: conflictsRepeater
                model: page.hasConflictModel ? page.conflicts : null
                delegate: TaskConflictRow {
                    required property string trackId
                    required property string fileName
                    required property string summary
                    required property string conflictState
                    required property string errorMessage
                    width: column.width
                    title: fileName
                    detail: summary
                    stage: conflictState
                    error: errorMessage
                    onReplaceRequested: page.conflicts.resolve(trackId)
                    onDismissRequested: page.conflicts.dismiss(trackId)
                }
            }

            SectionLabel {
                visible: page.active > 0
                text: "Running"
            }

            Repeater {
                model: jobsModel
                delegate: JobCard {
                    width: column.width
                    visible: canCancel
                }
            }

            SectionLabel {
                visible: page.finished > 0
                text: "Finished"
            }

            Repeater {
                model: jobsModel
                delegate: JobCard {
                    width: column.width
                    visible: !canCancel
                }
            }

            Text {
                visible: page.active === 0 && page.finished === 0
                width: parent.width
                text: "No background tasks in this session."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    component JobCard: Rectangle {
        id: card

        required property string jobId
        required property string label
        required property string jobState
        required property string outcome
        required property string stateLabel
        required property real progress
        required property int completed
        required property int total
        required property string detail
        required property real elapsedSeconds
        required property real remainingSeconds
        required property string errorMessage
        required property int failureCount
        required property var failures
        required property bool canCancel

        implicitHeight: body.implicitHeight + 28
        height: visible ? implicitHeight : 0
        color: Theme.surface
        radius: 6

        TaskRow {
            id: body
            x: 16
            y: 14
            width: card.width - 32
            jobId: card.jobId
            label: card.label
            jobState: card.jobState
            outcome: card.outcome
            stateLabel: card.stateLabel
            progress: card.progress
            completed: card.completed
            total: card.total
            detail: card.detail
            elapsedSeconds: card.elapsedSeconds
            remainingSeconds: card.remainingSeconds
            errorMessage: card.errorMessage
            failureCount: card.failureCount
            failures: card.failures
            canCancel: card.canCancel
            onCancelRequested: jobsModel.cancel(card.jobId)
        }
    }
}
