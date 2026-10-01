import QtQuick

Item {
    id: queue
    required property var workspace
    property int bottomInset: 0
    objectName: "queuePanel"

    PlaybackQueueView {
        anchors.fill: parent
        player: queue.workspace.playerModel
        workspace: queue.workspace
        bottomInset: queue.bottomInset
    }
}
