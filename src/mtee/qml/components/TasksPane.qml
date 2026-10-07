import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Tag conflicts waiting for the user, then the background jobs of this session in three
// groups: what runs now (a job that just succeeded stays there a few seconds), what needs
// attention (failed or partly done, with a link to the details on the Tasks page) and,
// collapsed, everything else that finished.
Item {
    id: pane

    required property var workspace
    readonly property var conflicts: workspace.tagConflicts
    readonly property bool hasConflictModel: conflicts && typeof conflicts.count === "number"
    property bool doneOpen: false

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
                visible: jobsModel.liveCount > 0
                text: "Running"
            }

            Repeater {
                model: jobsModel
                delegate: TaskRow {
                    id: live

                    // Bound by hand: a ``required property`` named like one of TaskRow's own
                    // would shadow it, and the row would stay empty.
                    required property var model

                    jobId: model.jobId
                    label: model.label
                    jobState: model.jobState
                    outcome: model.outcome
                    stateLabel: model.stateLabel
                    progress: model.progress
                    completed: model.completed
                    total: model.total
                    detail: model.detail
                    elapsedSeconds: model.elapsedSeconds
                    remainingSeconds: model.remainingSeconds
                    errorMessage: model.errorMessage
                    canCancel: model.canCancel
                    width: content.width
                    visible: model.group === "live"
                    compact: true
                    onCancelRequested: jobsModel.cancel(model.jobId)
                }
            }

            SectionLabel {
                visible: jobsModel.attentionCount > 0
                text: "Needs attention (" + jobsModel.attentionCount + ")"
            }

            Repeater {
                model: jobsModel
                delegate: Rectangle {
                    id: attention

                    required property string label
                    required property string outcome
                    required property string stateLabel
                    required property int total
                    required property int failureCount
                    required property string group
                    readonly property color accent: outcome === "partial" ? Theme.warning : Theme.danger

                    objectName: "taskAttentionRow"
                    visible: group === "attention"
                    width: content.width
                    height: visible ? body.implicitHeight + 20 : 0
                    color: Theme.surface
                    radius: 4

                    Rectangle {
                        width: 3
                        height: parent.height
                        radius: 2
                        color: attention.accent
                    }

                    Column {
                        id: body
                        x: 14
                        y: 10
                        width: parent.width - 24
                        spacing: 3

                        Text {
                            width: parent.width
                            text: attention.label
                            elide: Text.ElideRight
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSecondary
                        }

                        Text {
                            width: parent.width
                            text: {
                                if (attention.outcome === "partial" && attention.total > 0)
                                    return (attention.total - attention.failureCount) + " / " + attention.total
                                        + " done · " + attention.failureCount + " failed"
                                return attention.stateLabel
                            }
                            elide: Text.ElideRight
                            color: attention.accent
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        TextButton {
                            objectName: "taskDetails"
                            text: "Details"
                            kind: "ghost"
                            implicitHeight: 24
                            onClicked: pane.workspace.openTasks()
                        }
                    }
                }
            }

            Item {
                visible: jobsModel.settledCount > 0
                width: parent.width
                height: 24

                Icon {
                    id: doneChevron
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    name: pane.doneOpen ? "chevron-down" : "chevron-right"
                    size: 14
                    color: Theme.textSecondary
                }

                Text {
                    anchors.left: doneChevron.right
                    anchors.leftMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    text: jobsModel.settledCount + " finished"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                MouseArea {
                    objectName: "taskDoneToggle"
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: pane.doneOpen = !pane.doneOpen
                }
            }

            Repeater {
                model: jobsModel
                delegate: Item {
                    id: done

                    required property string label
                    required property string jobState
                    required property real elapsedSeconds
                    required property string group

                    visible: pane.doneOpen && group === "done"
                    width: content.width
                    height: visible ? 22 : 0

                    Icon {
                        id: doneIcon
                        anchors.left: parent.left
                        anchors.leftMargin: 2
                        anchors.verticalCenter: parent.verticalCenter
                        name: done.jobState === "succeeded" ? "check" : "close"
                        size: 12
                        color: Theme.textMuted
                    }

                    Text {
                        anchors.left: doneIcon.right
                        anchors.leftMargin: 8
                        anchors.right: doneTime.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: done.label
                        elide: Text.ElideRight
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    Text {
                        id: doneTime
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: {
                            const whole = Math.max(0, Math.floor(done.elapsedSeconds))
                            const rest = whole % 60
                            return Math.floor(whole / 60) + ":" + (rest < 10 ? "0" : "") + rest
                        }
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        font.features: { "tnum": 1 }
                    }
                }
            }

            Item {
                visible: jobsModel.settledCount > 0 || jobsModel.attentionCount > 0
                width: parent.width
                height: 28

                TextButton {
                    objectName: "taskClearFinished"
                    anchors.left: parent.left
                    text: "Clear finished"
                    kind: "ghost"
                    implicitHeight: 24
                    onClicked: jobsModel.clearFinished()
                }
            }

            Text {
                visible: jobsModel.liveCount + jobsModel.attentionCount + jobsModel.settledCount === 0
                width: parent.width
                text: "No background tasks in this session."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.WordWrap
            }
        }
    }
}
