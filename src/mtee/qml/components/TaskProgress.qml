import QtQuick
import Mtee

// The task progress strip of the header (plan 134.3, U8). Hidden when no job runs. Otherwise it
// shows the label of the most recently started running job, its completed/total count when known,
// a thin bar (sweeping when the total is unknown) and +N for the others. Below 1 100 px only the bar
// and +N remain; below 760 px a small ring icon. A click lists every running job with Cancel.
Item {
    id: strip

    // The width of the window: the strip keeps less of itself as the window narrows.
    property int windowWidth: 1440
    // The running jobs as JobsListModel.runningJobs() gives them, most recently started first.
    property var running: []
    readonly property var current: running.length > 0 ? running[0] : null
    readonly property int moreCount: Math.max(0, running.length - 1)
    readonly property bool ringOnly: windowWidth < 760
    readonly property bool barOnly: windowWidth < 1100
    readonly property bool indeterminate: current !== null && current.total < 0
    readonly property string countText: {
        if (current === null || current.total <= 0 || current.completed < 0)
            return ""
        return current.completed + " / " + current.total
    }

    objectName: "taskProgress"
    visible: running.length > 0
    height: Theme.frameSize
    width: !visible ? 0 : ringOnly ? 32 : barOnly ? 180 : 260

    function refresh() {
        running = jobsModel.runningJobs()
    }

    Connections {
        target: jobsModel
        function onDataChanged() { strip.refresh() }
        function onRowsInserted() { strip.refresh() }
        function onRowsRemoved() { strip.refresh() }
        function onModelReset() { strip.refresh() }
    }

    Component.onCompleted: refresh()

    // Ring mode: a ring around the tasks icon.
    Rectangle {
        objectName: "taskProgressRing"
        visible: strip.ringOnly && strip.visible
        anchors.centerIn: parent
        width: 24
        height: 24
        radius: 12
        color: "transparent"
        border.width: 2
        border.color: Theme.primary

        Icon {
            anchors.centerIn: parent
            name: "tasks"
            size: 12
            color: Theme.primary
        }
    }

    // Bar mode and wide mode.
    Item {
        id: body
        objectName: "taskProgressBody"
        visible: !strip.ringOnly && strip.visible
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 7
        anchors.bottomMargin: 7

        Text {
            id: labelText
            objectName: "taskProgressLabel"
            visible: !strip.barOnly
            anchors.left: parent.left
            anchors.right: countText.left
            anchors.rightMargin: 8
            anchors.top: parent.top
            text: strip.current ? strip.current.label : ""
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            id: countText
            objectName: "taskProgressCount"
            visible: !strip.barOnly && text.length > 0
            anchors.right: moreText.visible ? moreText.left : parent.right
            anchors.rightMargin: moreText.visible ? 6 : 0
            anchors.top: parent.top
            text: strip.countText
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Text {
            id: moreText
            objectName: "taskProgressMore"
            visible: strip.moreCount > 0
            anchors.right: parent.right
            anchors.top: parent.top
            text: "+" + strip.moreCount
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        ProgressLine {
            id: bar
            objectName: "taskProgressBar"
            visible: !strip.indeterminate
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            progress: strip.current ? strip.current.progress : 0
            status: "running"
        }

        // The unknown total: a segment that sweeps along the bar.
        Rectangle {
            id: sweep
            objectName: "taskProgressSweep"
            visible: strip.indeterminate
            y: body.height - 3
            width: body.width * 0.3
            height: 3
            color: Theme.primary

            SequentialAnimation on x {
                running: sweep.visible
                loops: Animation.Infinite
                NumberAnimation { from: -sweep.width; to: body.width; duration: 1200 }
            }
        }
    }

    Popover {
        id: popover
        objectName: "taskPopover"
        anchorItem: strip
        bodyWidth: 380
        maxHeight: 520

        Column {
            id: list
            width: parent.width
            spacing: 14

            SectionLabel {
                text: "Running (" + strip.running.length + ")"
            }

            Repeater {
                model: strip.running

                delegate: TaskRow {
                    required property var modelData

                    width: list.width
                    jobId: modelData.jobId
                    label: modelData.label
                    jobState: modelData.jobState
                    outcome: modelData.outcome
                    stateLabel: modelData.stateLabel
                    progress: modelData.progress
                    completed: modelData.completed
                    total: modelData.total
                    detail: modelData.detail
                    elapsedSeconds: modelData.elapsedSeconds
                    remainingSeconds: modelData.remainingSeconds
                    errorMessage: modelData.errorMessage
                    canCancel: modelData.canCancel
                    onCancelRequested: jobsModel.cancel(modelData.jobId)
                }
            }
        }
    }

    MouseArea {
        id: stripMouse
        objectName: "taskProgressButton"
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (!popover.opened)
                strip.refresh()
            popover.toggle()
        }
    }
}
