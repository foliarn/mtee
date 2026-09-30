import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Tag conflicts waiting for the user, then the background jobs of this session.
// Each conflict is listed like a changed file in a source-control view, with small
// buttons to replace its tags or to dismiss it.
Item {
    id: pane

    required property var workspace
    readonly property var conflicts: workspace.tagConflicts
    readonly property bool hasConflictModel: conflicts && typeof conflicts.count === "number"

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
                delegate: ConflictRow {
                    required property string trackId
                    required property string fileName
                    required property string summary
                    required property string conflictState
                    required property string errorMessage
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

    component ConflictRow: Column {
        id: conflictRow

        property string title: ""
        property string detail: ""
        property string stage: "pending"
        property string error: ""
        readonly property bool working: stage === "working"
        signal replaceRequested()
        signal dismissRequested()

        objectName: "tagConflictRow"
        width: content.width
        spacing: 2

        Item {
            width: parent.width
            height: 24

            Icon {
                id: conflictIcon
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                name: "alert"
                size: 14
                color: conflictRow.error.length > 0 ? Theme.danger : Theme.textSecondary
            }

            Text {
                anchors.left: conflictIcon.right
                anchors.leftMargin: 6
                anchors.right: conflictButtons.left
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                text: conflictRow.title
                elide: Text.ElideMiddle
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Row {
                id: conflictButtons
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                IconButton {
                    objectName: "replaceConflict"
                    width: 22
                    height: 22
                    icon: "check"
                    iconSize: 14
                    enabledAction: !conflictRow.working
                    tip: "Replace: delete the old tag values of this track and write the new ones"
                    onClicked: conflictRow.replaceRequested()
                }

                IconButton {
                    objectName: "dismissConflict"
                    width: 22
                    height: 22
                    icon: "close"
                    iconSize: 14
                    enabledAction: !conflictRow.working
                    tip: "Dismiss without writing"
                    onClicked: conflictRow.dismissRequested()
                }
            }
        }

        Text {
            width: parent.width - 20
            x: 20
            text: conflictRow.detail
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Text {
            visible: conflictRow.working
            width: parent.width - 20
            x: 20
            text: "Replacing\u2026"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Text {
            visible: conflictRow.error.length > 0
            width: parent.width - 20
            x: 20
            text: conflictRow.error
            wrapMode: Text.WordWrap
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
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
