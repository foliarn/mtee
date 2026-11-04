import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../components"

// Tasks window (plan 134.5): a center tab. Left, the session's tasks (unfinished first, then the
// finished ones, newest first) as nav rows with a state tag; right, the record of the selected
// task: summary, times, counts, the items that failed and Cancel while it runs. Opened from the
// hamburger menu or from a notification's Details, which selects the task (taskFocusRequested).
Rectangle {
    id: page

    required property var workspace
    property int bottomInset: 0
    property string selectedId: ""
    property var tasks: []
    property var detail: ({})
    readonly property int active: jobsModel.activeCount
    readonly property int finished: jobsModel.finishedCount
    readonly property bool hasDetail: detail.jobId !== undefined
    readonly property bool isActive: hasDetail && (detail.jobState === "running" || detail.jobState === "queued")
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

    function formatClock(seconds) {
        const whole = Math.max(0, Math.floor(seconds))
        const hours = Math.floor(whole / 3600)
        const minutes = Math.floor((whole % 3600) / 60)
        const rest = whole % 60
        const two = (value) => (value < 10 ? "0" : "") + value
        return hours > 0 ? hours + ":" + two(minutes) + ":" + two(rest) : minutes + ":" + two(rest)
    }

    function formatLeft(seconds) {
        if (seconds < 60)
            return "Less than a minute left"
        const minutes = Math.ceil(seconds / 60)
        if (minutes < 60)
            return "About " + minutes + " min left"
        return "About " + Math.floor(minutes / 60) + " hr " + (minutes % 60) + " min left"
    }

    function formatTime(seconds) {
        if (!(seconds > 0))
            return "-"
        return new Date(seconds * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat)
    }

    // Reads the task list and the selected record again (on every job change and clock tick).
    function refresh() {
        tasks = jobsModel.taskList()
        let found = false
        for (let i = 0; i < tasks.length; ++i) {
            if (tasks[i].jobId === selectedId)
                found = true
        }
        if (!found)
            selectedId = tasks.length > 0 ? tasks[0].jobId : ""
        detail = selectedId.length > 0 ? jobsModel.taskDetail(selectedId) : ({})
    }

    function select(jobId) {
        selectedId = jobId
        refresh()
    }

    Component.onCompleted: refresh()

    Connections {
        target: jobsModel
        function onDataChanged() { page.refresh() }
        function onRowsInserted() { page.refresh() }
        function onRowsRemoved() { page.refresh() }
        function onModelReset() { page.refresh() }
    }

    Connections {
        target: page.workspace
        function onTaskFocusRequested(jobId) {
            if (jobId.length > 0)
                page.select(jobId)
        }
    }

    // Left: the summary, the clear button and the task list.
    Item {
        id: sidebar
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.bottomInset
        width: Math.min(320, Math.max(220, page.width * 0.34))

        Column {
            id: heading
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 16
            spacing: 2

            SectionLabel { text: "Tasks" }

            Text {
                objectName: "tasksSummary"
                width: parent.width
                text: page.summary
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                objectName: "clearFinishedTasks"
                anchors.right: parent.right
                text: "Clear finished"
                kind: "ghost"
                implicitHeight: 24
                enabledAction: page.finished > 0
                onClicked: jobsModel.clearFinished()
            }
        }

        NavList {
            id: taskList
            objectName: "taskList"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: heading.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: 8
            size: "regular"
            model: page.tasks
            rowObjectName: "taskRow"
            selectionEnabled: false
            selectedIds: page.selectedId.length > 0 ? [page.selectedId] : []
            onRowClicked: (rowId, modifiers) => page.select(rowId)

        }

        Text {
            anchors.horizontalCenter: taskList.horizontalCenter
            anchors.top: taskList.top
            anchors.topMargin: 24
            visible: page.tasks.length === 0
            width: sidebar.width - 32
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "No background tasks in this session."
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }

    Rectangle {
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: Theme.separator
    }

    // Right: the record of the selected task.
    Flickable {
        id: scroller
        anchors.left: sidebar.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.bottomInset
        contentHeight: detailColumn.implicitHeight + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        WheelScrollHandler { flickable: scroller }
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: detailColumn
            x: 24
            y: 24
            width: Math.min(640, scroller.width - 48)
            spacing: 14
            visible: page.hasDetail

            Text {
                objectName: "taskTitle"
                width: parent.width
                text: page.detail.label || ""
                wrapMode: Text.WordWrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeHeading
                font.weight: Font.Bold
            }

            Row {
                spacing: 8

                TagChip {
                    objectName: "taskState"
                    text: page.detail.stateLabel || ""
                    tone: page.detail.tagTone || "neutral"
                }

                TextButton {
                    objectName: "taskCancel"
                    visible: page.detail.canCancel === true
                    text: "Cancel"
                    kind: "ghost"
                    implicitHeight: 24
                    onClicked: jobsModel.cancel(page.selectedId)
                }
            }

            Text {
                objectName: "taskSummary"
                width: parent.width
                visible: text.length > 0
                text: page.detail.summary || (page.isActive ? "" : page.detail.detail || "")
                wrapMode: Text.WordWrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            ProgressLine {
                visible: page.isActive
                width: parent.width
                progress: page.detail.progress || 0
                status: "running"
            }

            // The facts of the record: started, finished or elapsed, counts.
            Grid {
                id: facts
                columns: 2
                columnSpacing: 24
                rowSpacing: 6

                Text { text: "Started"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }
                Text {
                    objectName: "taskStarted"
                    text: page.formatTime(page.detail.startedAt || 0)
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text {
                    text: "Finished"
                    visible: !page.isActive
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                Text {
                    objectName: "taskFinished"
                    visible: !page.isActive
                    text: page.formatTime(page.detail.finishedAt || 0)
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text {
                    text: page.isActive ? "Elapsed" : "Duration"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                Text {
                    objectName: "taskDuration"
                    text: page.formatClock(page.detail.elapsedSeconds || 0)
                        + (page.isActive && (page.detail.remainingSeconds || -1) >= 0
                            ? " · " + page.formatLeft(page.detail.remainingSeconds) : "")
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text {
                    visible: (page.detail.total || -1) > 0 || (page.detail.completed || -1) >= 0
                    text: "Counts"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                Text {
                    objectName: "taskCounts"
                    visible: text.length > 0
                    text: {
                        const total = page.detail.total || -1
                        const done = page.detail.completed || -1
                        let head = ""
                        if (total > 0)
                            head = done + " of " + total
                        else if (done >= 0)
                            head = done.toLocaleString(Qt.locale("en_US"), "f", 0) + " done"
                        const failed = page.detail.failureCount || 0
                        if (failed > 0)
                            head += (head.length > 0 ? " · " : "") + failed + " failed"
                        return head
                    }
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }

            Text {
                objectName: "taskError"
                visible: (page.detail.errorMessage || "").length > 0
                width: parent.width
                text: page.detail.errorMessage || ""
                wrapMode: Text.WordWrap
                color: Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            SectionLabel {
                visible: (page.detail.failureCount || 0) > 0
                text: "Items that failed (" + (page.detail.failureCount || 0) + ")"
            }

            Column {
                id: failureList
                objectName: "taskFailures"
                width: parent.width
                spacing: 10
                visible: (page.detail.failureCount || 0) > 0

                Repeater {
                    model: page.detail.failures || []

                    delegate: Rectangle {
                        id: failureCard

                        required property var modelData

                        width: failureList.width
                        height: failureColumn.implicitHeight + 24
                        color: Theme.surface
                        radius: Theme.radius

                        Column {
                            id: failureColumn
                            x: 14
                            y: 12
                            width: failureCard.width - 28
                            spacing: 4

                            Text {
                                width: parent.width
                                text: failureCard.modelData.name
                                elide: Text.ElideMiddle
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                                font.weight: Font.DemiBold
                            }

                            Text {
                                width: parent.width
                                text: failureCard.modelData.message
                                wrapMode: Text.WordWrap
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }

                            TextButton {
                                objectName: "taskShowInFolder"
                                visible: /^([A-Za-z]:[\\/]|\/)/.test(failureCard.modelData.name)
                                text: "Show in folder"
                                kind: "ghost"
                                implicitHeight: 24
                                onClicked: jobsModel.showInFolder(failureCard.modelData.name)
                            }
                        }
                    }
                }
            }
        }

        Text {
            x: 24
            y: 24
            visible: !page.hasDetail
            width: Math.min(640, scroller.width - 48)
            text: "Select a task on the left to see its record."
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }
}
