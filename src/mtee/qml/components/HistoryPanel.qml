import QtQuick

// History tab of the right panel: the last listenings, most recent first.
Item {
    id: history
    required property var workspace
    property int bottomInset: 0
    objectName: "historyPanel"

    HistoryList {
        anchors.fill: parent
        anchors.bottomMargin: history.bottomInset
        workspace: history.workspace
    }
}
