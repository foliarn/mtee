import QtQuick
import Mtee

// Table view of the foundation step: fictitious rows, default columns of
// PLAN.md (Title, Artist, Genre, BPM, Key) plus Duration and Format.
// Rows are reused by the ListView; no permanent item is created per file.
Item {
    id: table

    property alias model: rows.model
    property int currentRow: 0
    property int playingRow: 1

    // Default columns of PLAN.md, then Duration and Format. The weights keep the
    // short columns readable when the pane is narrow.
    readonly property var columns: [
        { "role": "title", "title": "Title", "weight": 3 },
        { "role": "artist", "title": "Artist", "weight": 2 },
        { "role": "genre", "title": "Genre", "weight": 2 },
        { "role": "bpm", "title": "BPM", "weight": 0.9 },
        { "role": "musicalKey", "title": "Key", "weight": 0.9 },
        { "role": "duration", "title": "Duration", "weight": 1.3 },
        { "role": "fileFormat", "title": "Format", "weight": 1.3 }
    ]
    readonly property real weightTotal: 11.4

    Row {
        id: header
        height: Theme.rowHeight
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Theme.spacing
        anchors.rightMargin: Theme.spacing

        Repeater {
            model: table.columns
            delegate: Item {
                required property var modelData
                width: (table.width - 2 * Theme.spacing) * modelData.weight / table.weightTotal
                height: header.height

                SectionLabel {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - Theme.spacingSmall
                    text: parent.modelData.title
                }
            }
        }
    }

    Rectangle {
        id: separator
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.border
    }

    ListView {
        id: rows
        anchors.top: separator.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true

        delegate: Rectangle {
            id: row
            required property int index
            required property string title
            required property string artist
            required property string genre
            required property string bpm
            required property string musicalKey
            required property string duration
            required property string fileFormat

            width: rows.width
            height: Theme.rowHeight
            color: table.currentRow === index
                ? Theme.selection
                : hover.hovered
                    ? Theme.hover
                    : "transparent"

            readonly property var values: [title, artist, genre, bpm, musicalKey, duration, fileFormat]

            Rectangle {
                width: 3
                height: parent.height
                color: Theme.accent
                visible: table.playingRow === row.index
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: Theme.spacing
                anchors.rightMargin: Theme.spacing

                Repeater {
                    model: table.columns
                    delegate: Item {
                        required property int index
                        required property var modelData
                        width: (rows.width - 2 * Theme.spacing) * modelData.weight / table.weightTotal
                        height: Theme.rowHeight

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - Theme.spacingSmall
                            elide: Text.ElideRight
                            text: row.values[parent.index]
                            color: parent.index === 0 ? Theme.textPrimary : Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                            font.bold: parent.index === 0 && table.playingRow === row.index
                        }
                    }
                }
            }

            HoverHandler { id: hover }

            TapHandler {
                onSingleTapped: table.currentRow = row.index
                onDoubleTapped: table.playingRow = row.index
            }
        }
    }
}
