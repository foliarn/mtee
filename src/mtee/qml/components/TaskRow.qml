import QtQuick
import QtQuick.Controls.Basic
import Mtee

// One background task: label and state, "42 / 129 · current item", a progress line, the
// time spent and left, and the items that failed. ``compact`` is the sidebar version.
Column {
    id: task

    property string jobId: ""
    property string label: ""
    property string jobState: "running"
    property string stateLabel: ""
    property real progress: 0
    property int completed: -1
    property int total: -1
    property string detail: ""
    property real elapsedSeconds: 0
    property real remainingSeconds: -1
    property string errorMessage: ""
    property int failureCount: 0
    property var failures: []
    property bool canCancel: false
    property bool compact: false
    property bool failuresOpen: false
    signal cancelRequested()

    readonly property bool active: jobState === "running" || jobState === "queued"
    readonly property string barStatus: jobState === "failed" ? "error" : active ? "running" : "done"
    readonly property string countLine: {
        const where = task.detail.length > 0 ? task.detail : ""
        let head = ""
        if (task.total > 0)
            head = task.completed + " / " + task.total
        else if (task.completed >= 0)
            head = task.completed.toLocaleString(Qt.locale("en_US"), "f", 0) + " files"
        if (head.length > 0 && where.length > 0)
            return head + " · " + where
        return head.length > 0 ? head : where
    }
    readonly property string timeLine: {
        if (task.jobState === "queued")
            return "Waiting to start"
        if (task.active) {
            const spent = "Elapsed " + task.formatClock(task.elapsedSeconds)
            return task.remainingSeconds >= 0
                ? spent + " · " + task.formatLeft(task.remainingSeconds) : spent
        }
        const verb = task.jobState === "succeeded" ? "Finished in"
            : task.jobState === "cancelled" ? "Cancelled after"
            : task.stateLabel === "Interrupted" ? "Interrupted after" : "Failed after"
        return verb + " " + task.formatClock(task.elapsedSeconds)
    }

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

    objectName: "taskRow"
    spacing: compact ? 3 : 5

    Item {
        width: parent.width
        height: task.compact ? 18 : 22

        Icon {
            id: failIcon
            visible: task.jobState === "failed"
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            name: "alert"
            size: 14
            color: Theme.danger
        }

        Text {
            anchors.left: failIcon.visible ? failIcon.right : parent.left
            anchors.leftMargin: failIcon.visible ? 6 : 0
            anchors.right: stateText.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: task.label
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: task.compact ? Theme.fontSizeSecondary : Theme.fontSizeBody
            font.weight: task.compact ? Font.Normal : Font.DemiBold
        }

        Text {
            id: stateText
            visible: !task.compact || !task.canCancel
            anchors.right: cancelButton.visible ? cancelButton.left : parent.right
            anchors.rightMargin: cancelButton.visible ? 4 : 0
            anchors.verticalCenter: parent.verticalCenter
            text: task.stateLabel
            color: task.jobState === "failed" ? Theme.danger
                : task.active ? Theme.primary : Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        IconButton {
            id: cancelButton
            objectName: "taskCancel"
            visible: task.canCancel
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: 22
            height: 22
            icon: "close"
            iconSize: 14
            tip: "Cancel"
            onClicked: task.cancelRequested()
        }
    }

    Text {
        visible: task.countLine.length > 0
        width: parent.width
        text: task.countLine
        elide: Text.ElideMiddle
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: task.compact ? Theme.fontSizeSmall : Theme.fontSizeSecondary
    }

    ProgressLine {
        width: parent.width
        progress: task.progress
        status: task.barStatus
    }

    Text {
        visible: !task.compact || task.active
        width: parent.width
        text: task.timeLine
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Text {
        visible: task.errorMessage.length > 0
        width: parent.width
        text: task.errorMessage
        wrapMode: Text.WordWrap
        color: Theme.danger
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Item {
        visible: task.failureCount > 0 && !task.compact
        width: parent.width
        height: visible ? 24 : 0

        Icon {
            id: failureChevron
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            name: task.failuresOpen ? "chevron-down" : "chevron-right"
            size: 14
            color: Theme.textSecondary
        }

        Text {
            anchors.left: failureChevron.right
            anchors.leftMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: task.failureCount + (task.failureCount === 1 ? " item failed" : " items failed")
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        MouseArea {
            objectName: "taskFailuresToggle"
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: task.failuresOpen = !task.failuresOpen
        }
    }

    Flickable {
        id: failureList
        visible: task.failuresOpen && task.failureCount > 0 && !task.compact
        width: parent.width
        height: visible ? Math.min(240, failureColumn.implicitHeight) : 0
        contentHeight: failureColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: failureColumn
            width: failureList.width - 10
            spacing: 6

            Repeater {
                model: task.failuresOpen ? task.failures : []

                delegate: Row {
                    required property var modelData
                    width: failureColumn.width
                    spacing: 8

                    Icon {
                        name: "alert"
                        size: 12
                        color: Theme.danger
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        width: parent.width - 20
                        text: parent.modelData.name + " — " + parent.modelData.message
                        wrapMode: Text.WordWrap
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }
            }
        }
    }
}
