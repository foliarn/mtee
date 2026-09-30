import QtQuick
import Mtee

Item {
    id: header
    required property var workspace
    required property var tab
    required property var trackModel
    readonly property var details: { workspace.revision; return workspace.playlistModel.details(tab.ref) }
    readonly property int coverSize: width < 800 ? 164 : 208
    PlaylistCover {
        id: cover
        x: 24; y: 24
        width: header.coverSize; height: width
        source: header.details.coverUrl || ""
        covers: header.details.covers || []
        MouseArea {
            anchors.fill: parent
            enabled: header.tab.ref !== "liked"
            cursorShape: Qt.PointingHandCursor
            onClicked: header.workspace.playlistModel.requestUI("cover", header.tab.ref, [])
        }
    }
    Column {
        x: cover.x + cover.width + 28
        y: 40
        width: parent.width - x - 24
        spacing: 12
        Text {
            width: parent.width
            text: header.details.name || header.tab.title
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: header.width < 800 ? 36 : 52
            font.weight: Font.Bold
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: header.details.description || ""
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: header.workspace.playlistModel.creator + " · " + (header.details.summary || "")
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            elide: Text.ElideRight
        }
        TextButton {
            visible: header.tab.ref !== "liked"
            text: "Edit playlist"; kind: "ghost"
            onClicked: header.workspace.playlistModel.requestUI("edit", header.tab.ref, [])
        }
    }
    Row {
        x: 24
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        spacing: 16
        IconButton {
            objectName: "playlistPlay"
            width: 56; height: 56
            icon: "play"; iconSize: 24; iconColor: Theme.editor
            color: Theme.primary; radius: width / 2; hoverColor: Theme.editor
            tip: "Play visible tracks"
            onClicked: header.workspace.playPlaylistRows(header.tab.ref, header.trackModel.rows, false)
        }
        IconButton {
            objectName: "playlistShuffle"
            anchors.verticalCenter: parent.verticalCenter
            icon: "shuffle"; iconSize: 24; tip: "Shuffle visible tracks"
            onClicked: header.workspace.playPlaylistRows(header.tab.ref, header.trackModel.rows, true)
        }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
}
