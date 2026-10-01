import QtQuick

// Queue tab of the right panel: the same list as page 2 of the fullscreen player.
Item {
    id: queue
    required property var workspace
    property int bottomInset: 0
    objectName: "queuePanel"

    QueueList {
        anchors.fill: parent
        anchors.bottomMargin: queue.bottomInset
        workspace: queue.workspace
        horizontalPadding: 12
        rightPadding: 10
        labelInset: 12
        listObjectName: "queuePanelList"
    }
}
