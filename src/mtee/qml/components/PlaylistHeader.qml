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
        Rectangle {
            objectName: "playlistCoverHover"
            anchors.fill: parent
            color: "#73000000"
            visible: coverHit.containsMouse && header.tab.ref !== "liked"
            Text {
                anchors.centerIn: parent
                text: "Change cover"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
            }
        }
        MouseArea {
            id: coverHit
            anchors.fill: parent
            enabled: header.tab.ref !== "liked"
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: header.workspace.playlistModel.requestUI("cover", header.tab.ref, [])
        }
    }
    Item {
        x: cover.x + cover.width + 28
        y: cover.y
        width: parent.width - x - 24
        height: cover.height
        Text {
            y: 0
            text: "PLAYLIST"
            visible: header.tab.ref !== "liked"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeCaption
            font.weight: Font.DemiBold
        }
        Text {
            y: header.width < 800 ? 38 : 54
            objectName: "playlistTitleText"
            width: parent.width
            text: header.details.name || header.tab.title
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: header.width < 800 ? 36 : 52
            font.weight: Font.Bold
            elide: Text.ElideRight
            MouseArea {
                anchors.fill: parent
                enabled: header.tab.ref !== "liked"
                cursorShape: Qt.PointingHandCursor
                onClicked: header.workspace.playlistModel.requestUI("edit", header.tab.ref, [])
            }
        }
        Text {
            y: header.width < 800 ? 105 : 137
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
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 10
            width: parent.width
            text: header.workspace.playlistModel.creator + " · " + (header.details.summary || "")
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            elide: Text.ElideRight
        }
    }
    Row {
        x: 24
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
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
