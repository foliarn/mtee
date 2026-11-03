import QtQuick
import Mtee

// The status bar (plan 125.5): one strip under the whole window, under the player bar, 24 px high.
// Each row of ``items`` (StatusBarModel) is an icon, a text and an optional progress; a click runs
// the plugin's action. The strip is not drawn while no plugin gives an item, so the window keeps
// its height.
Rectangle {
    id: bar

    // The StatusBarModel of the workspace; undefined in the demo, which has no plugins.
    property var items: null
    readonly property int count: items ? items.count : 0

    objectName: "statusBar"
    height: 24
    color: Theme.chrome
    visible: count > 0

    Rectangle {
        width: parent.width
        height: 1
        color: Theme.separator
    }

    Row {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.topMargin: 1
        anchors.bottom: parent.bottom

        Repeater {
            model: bar.items

            delegate: Rectangle {
                id: entry

                readonly property color toneColor: model.tone === "warning" ? Theme.warning
                    : model.tone === "secondary" ? Theme.secondary : Theme.textSecondary

                objectName: "statusItem"
                height: parent.height
                width: row.implicitWidth + 24
                color: entryMouse.containsMouse && model.clickable ? Theme.surface : "transparent"

                Row {
                    id: row
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: model.icon
                        size: 14
                        color: entry.toneColor
                    }

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        objectName: "statusItemText"
                        text: model.text
                        color: entry.toneColor
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    // A thin progress line, 72 px, as the task progress lines are drawn.
                    Rectangle {
                        visible: model.progress >= 0
                        anchors.verticalCenter: parent.verticalCenter
                        width: 72
                        height: 3
                        color: Theme.selection

                        Rectangle {
                            width: parent.width * Math.max(0, Math.min(1, model.progress))
                            height: parent.height
                            color: Theme.primary
                        }
                    }
                }

                MouseArea {
                    id: entryMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: model.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: if (model.clickable) bar.items.activate(index)
                }

                HoverTip {
                    visible: entryMouse.containsMouse && model.tooltip.length > 0
                    text: model.tooltip
                }
            }
        }
    }
}
