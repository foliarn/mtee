import QtQuick
import Mtee

Item {
    id: pane
    required property var workspace
    property bool expanded: Boolean(workspace.genreManager)
    readonly property bool available: typeof workspace.openGenreManagerView === "function"
    readonly property string activePage: workspace.groups.length > 0
        ? String(workspace.groups[workspace.activeGroup].active).split(":")[1] || ""
        : ""

    PaneHeader {
        id: header
        width: parent.width
        title: pane.expanded ? "Genre Manager" : "Plugins"
        IconButton {
            visible: pane.expanded
            width: 26
            height: 26
            icon: "arrow-left"
            iconSize: 16
            tip: "All plugins"
            onClicked: pane.expanded = false
        }
    }

    Column {
        anchors.top: header.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 2

        Rectangle {
            visible: !pane.expanded
            x: 8
            width: parent.width - 16
            height: 52
            color: pluginMouse.containsMouse ? Theme.surface : "transparent"

            Column {
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Text {
                    text: "Genre Manager"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }
                Text {
                    text: "Classify and organize tracks"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
            MouseArea {
                id: pluginMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    pane.expanded = true
                    if (pane.available)
                        pane.workspace.openGenreManagerView("classify", "Genre Manager")
                }
            }
        }

        Repeater {
            model: pane.expanded ? [
                { "key": "classify", "label": "Classify" },
                { "key": "genres", "label": "Genres & tags" },
                { "key": "uncertain", "label": "Uncertain" }
            ] : []
            delegate: Rectangle {
                id: entry
                required property var modelData
                x: 8
                width: parent.width - 16
                height: 34
                color: pane.activePage === modelData.key ? Theme.selection
                    : entryMouse.containsMouse ? Theme.surface : "transparent"
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: entry.modelData.label
                    color: pane.activePage === entry.modelData.key ? Theme.textPrimary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                MouseArea {
                    id: entryMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: pane.workspace.openGenreManagerView(
                        entry.modelData.key, entry.modelData.label
                    )
                }
            }
        }
    }
}
