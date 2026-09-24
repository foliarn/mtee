import QtQuick
import Mtee

// Watermark of an editor group without tabs.
Rectangle {
    color: Theme.editor

    Column {
        anchors.centerIn: parent
        spacing: 18

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "M"
            color: Theme.surface
            font.family: Theme.fontFamily
            font.pixelSize: 120
            font.weight: Font.Black
        }

        Grid {
            anchors.horizontalCenter: parent.horizontalCenter
            columns: 2
            columnSpacing: 18
            rowSpacing: 8

            Repeater {
                model: [
                    "Show Explorer", "Ctrl+Shift+E",
                    "Split editor", "Ctrl+\\",
                    "Edit info", "Ctrl+I",
                    "Open Settings", "Ctrl+,"
                ]
                delegate: Text {
                    required property string modelData
                    required property int index
                    text: modelData
                    color: index % 2 === 0 ? Theme.textSecondary : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }
    }
}
