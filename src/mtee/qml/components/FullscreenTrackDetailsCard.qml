import QtQuick
import QtQuick.Layouts
import Mtee

// Details of the playing track: grey label, white value, "—" when a value is missing.
// The folder is only the name of the parent folder, never the full path.
FullscreenCard {
    id: card

    required property var track
    // One label/value pair per row when there is room, otherwise two pairs per row.
    property bool single: true
    readonly property var fields: details(track)

    objectName: "fullscreenTrackDetailsCard"
    heading: "Track details"

    function textOf(value) {
        return value !== undefined && value !== null && String(value).length > 0 && value !== 0
            ? String(value) : ""
    }

    function sampleRateText(value) {
        const rate = Number(value)
        if (!isNaN(rate) && rate >= 1000)
            return (rate / 1000).toFixed(rate % 1000 === 0 ? 0 : 1) + " kHz"
        return textOf(value)
    }

    function folderName(track) {
        const path = textOf(track.path)
        if (path.length > 0) {
            const parts = path.split(/[\\/]/)
            return parts.length >= 2 ? parts[parts.length - 2] : ""
        }
        const folder = textOf(track.folder)
        return folder.length > 0 ? folder.split("/").pop() : ""
    }

    function formatText(track) {
        const container = textOf(track.format).toUpperCase()
        const codec = textOf(track.codec).toUpperCase()
        return codec.length > 0 && codec !== container ? container + " · " + codec : container
    }

    function details(track) {
        const bits = Number(track.bitsPerSample)
        return [
            {label: "BPM", value: textOf(track.bpmText) || textOf(track.bpm)},
            {label: "Key", value: textOf(track.key), camelot: textOf(track.keyCamelot)},
            {label: "Genre", value: textOf(track.genre)},
            {label: "Date", value: textOf(track.year)},
            {label: "Format", value: formatText(track)},
            {label: "Bitrate", value: textOf(track.bitrateText) || textOf(track.bitrate)},
            {label: "Folder", value: folderName(track)},
            {label: "Album", value: textOf(track.album)},
            {label: "Duration", value: textOf(track.duration)},
            {label: "Sample rate", value: sampleRateText(track.sampleRate)},
            {label: "Bit depth", value: bits > 0 ? bits + "-bit" : ""},
            {label: "Size", value: textOf(track.size)}
        ]
    }

    GridLayout {
        width: parent.width
        columns: card.single ? 1 : 2
        columnSpacing: 16
        rowSpacing: card.single ? 4 : 2

        Repeater {
            model: card.fields

            delegate: Item {
                id: cell

                required property var modelData
                readonly property real labelWidth: card.single ? 84 : 76
                readonly property bool hasBadge: modelData.camelot !== undefined && modelData.camelot.length > 0

                objectName: "detail_" + modelData.label
                Layout.fillWidth: true
                implicitHeight: card.single ? 20 : 18

                Text {
                    width: cell.labelWidth
                    text: cell.modelData.label
                    elide: Text.ElideRight
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: card.single ? Theme.fontSizeSecondary : Theme.fontSizeSmall
                }

                Row {
                    x: cell.labelWidth + 6
                    width: cell.width - x
                    spacing: 6

                    Text {
                        objectName: "detailValue"
                        width: Math.min(implicitWidth, parent.width - (cell.hasBadge ? 32 : 0))
                        text: cell.modelData.value.length > 0 ? cell.modelData.value : "—"
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: card.single ? Theme.fontSizeSecondary : Theme.fontSizeSmall
                    }

                    Rectangle {
                        visible: cell.hasBadge
                        width: camelotText.implicitWidth + 10
                        height: 16
                        radius: Theme.badgeRadius
                        color: Theme.camelotColor(cell.modelData.camelot || "")

                        Text {
                            id: camelotText
                            anchors.centerIn: parent
                            text: cell.modelData.camelot || ""
                            color: Theme.textOnColor
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }
                }
            }
        }
    }
}
