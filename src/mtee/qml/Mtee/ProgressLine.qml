import QtQuick

// Non-interactive progress of a task: primary while running, danger on error, warning when partly done.
Rectangle {
    id: line

    property real progress: 0
    property string status: "running"

    implicitHeight: 3
    color: Theme.selection

    Rectangle {
        width: parent.width * Math.max(0, Math.min(1, line.progress))
        height: parent.height
        color: line.status === "error" ? Theme.danger
            : line.status === "warning" ? Theme.warning
            : line.status === "done" ? Theme.textMuted
            : Theme.primary
    }
}
