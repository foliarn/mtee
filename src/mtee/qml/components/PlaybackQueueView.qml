import QtQuick
import Mtee

// The queue model belongs to the shared player and survives view changes.
Item {
    id: queueView

    required property var player
    property bool nextOnly: true

    objectName: "playbackQueueView"
    implicitHeight: rows.implicitHeight

    Column {
        id: rows
        width: parent.width

        Repeater {
            model: queueView.player.hasQueueModel ? queueView.player.queueModel : []

            delegate: Item {
                id: row
                required property var modelData
                required property int index

                readonly property bool isCurrent: modelData.current === true
                readonly property bool shown: !queueView.nextOnly || !isCurrent

                width: rows.width
                height: shown ? 48 : 0
                visible: shown

                Rectangle {
                    anchors.fill: parent
                    color: rowMouse.containsMouse ? Theme.surface : "transparent"
                }

                Text {
                    x: 16
                    width: 34
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.isCurrent ? "▶" : String(row.modelData.index + 1)
                    color: row.isCurrent ? Theme.primary : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    horizontalAlignment: Text.AlignHCenter
                }

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: 58
                    anchors.right: availability.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1

                    Text {
                        width: parent.width
                        text: row.modelData.title || row.modelData.filename || "Unknown track"
                        elide: Text.ElideRight
                        color: row.isCurrent ? Theme.primary : Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    Text {
                        width: parent.width
                        text: row.modelData.artist || "Unknown artist"
                        elide: Text.ElideRight
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }

                Text {
                    id: availability
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.available ? (row.modelData.duration || "") : "Unavailable"
                    color: row.modelData.available ? Theme.textMuted : Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: row.shown
                    onDoubleClicked: queueView.player.playIndex(row.modelData.index)
                }
            }
        }
    }
}
