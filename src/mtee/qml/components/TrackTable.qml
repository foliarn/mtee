import QtQuick
import Mtee

Item {
    id: table

    property var workspace
    property bool showOptional: false
    property string sortColumn: "Title"
    signal sortRequested(string column)

    readonly property var defaultColumns: [
        { "key": "title", "label": "Title", "weight": 2.8 },
        { "key": "artist", "label": "Artist", "weight": 2.1 },
        { "key": "genre", "label": "Genre", "weight": 1.5 },
        { "key": "bpm", "label": "BPM", "weight": 0.8 },
        { "key": "key", "label": "Key", "weight": 0.8 }
    ]
    readonly property var optionalColumns: [
        { "key": "duration", "label": "Duration", "weight": 1.0 },
        { "key": "format", "label": "Format", "weight": 0.9 },
        { "key": "filename", "label": "Filename", "weight": 2.0 }
    ]
    readonly property var columns: table.showOptional ? table.defaultColumns.concat(table.optionalColumns) : table.defaultColumns
    readonly property real weightTotal: table.showOptional ? 11.9 : 8.0

    function valueFor(track, key) {
        var value = track[key]
        return value === "" ? "—" : value
    }

    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.rowHeight
        color: Theme.background

        Row {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacing
            anchors.rightMargin: Theme.spacing

            Repeater {
                model: table.columns
                delegate: Item {
                    required property var modelData
                    width: (table.width - 2 * Theme.spacing) * modelData.weight / table.weightTotal
                    height: parent.height

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label + (table.sortColumn === modelData.label ? "  ↑" : "")
                        color: Theme.textSecondary
                        elide: Text.ElideRight
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            table.sortColumn = modelData.label
                            table.sortRequested(modelData.key)
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.border
    }

    ListView {
        id: rows
        anchors.top: parent.top
        anchors.topMargin: Theme.rowHeight
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        model: table.workspace ? table.workspace.tracks : []
        boundsBehavior: Flickable.StopAtBounds

        delegate: Rectangle {
            id: row
            required property int index
            required property var modelData
            width: rows.width
            height: Theme.rowHeight
            color: table.workspace.selectedRows.indexOf(row.index) >= 0
                ? Theme.selection
                : rowHover.hovered ? Theme.hover : "transparent"

            Rectangle {
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: 3
                color: Theme.accent
                visible: table.workspace.playingRow === row.index
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacing
                anchors.rightMargin: Theme.spacing

                Repeater {
                    model: table.columns
                    delegate: Item {
                        required property var modelData
                        width: (rows.width - 2 * Theme.spacing) * modelData.weight / table.weightTotal
                        height: Theme.rowHeight

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: table.valueFor(row.modelData, modelData.key)
                            color: modelData.key === "title" ? Theme.textPrimary : Theme.textSecondary
                            elide: Text.ElideRight
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                            font.bold: table.workspace.playingRow === row.index && modelData.key === "title"
                        }
                    }
                }
            }

            HoverHandler { id: rowHover }
            MouseArea {
                anchors.fill: parent
                onClicked: table.workspace.selectRow(row.index, mouse.modifiers & Qt.ControlModifier)
                onDoubleClicked: table.workspace.playRow(row.index)
            }
        }
    }
}
