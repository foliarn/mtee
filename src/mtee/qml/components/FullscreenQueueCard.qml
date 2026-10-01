import QtQuick
import Mtee

// Queue of the fullscreen player: the playing track, then "Next in queue" (manual
// additions) and "Next from: <source>" (the rest of the context), without history. The
// list itself is shared with the right panel (QueueList).
FullscreenCard {
    id: card

    required property var workspace
    readonly property var playback: workspace.playerModel

    objectName: "fullscreenQueueCard"
    heading: "Queue"

    QueueList {
        anchors.fill: parent
        workspace: card.workspace
        wheelGuard: true
        listObjectName: "fullscreenQueueList"
    }
}
