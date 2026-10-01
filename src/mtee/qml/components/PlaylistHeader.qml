import QtQuick
import QtQuick.Effects
import Mtee

// Playlist header laid out like Spotify's, in MTEE colours: a large rounded cover with a
// soft shadow, then "Playlist", the title in the display font, the description and
// "creator • N tracks, 34 min 26 sec" aligned on the bottom of the cover; Play and Shuffle
// sit below. No colour is taken from the cover.
Item {
    id: header
    required property var workspace
    required property var tab
    required property var trackModel
    readonly property var details: { workspace.revision; return workspace.playlistModel.details(tab.ref) }
    readonly property bool compact: width < 800
    readonly property int coverSize: compact ? Theme.playlistCoverCompact : Theme.playlistCoverLarge
    readonly property int playRow: 56
    readonly property bool editable: tab.ref !== "liked"
    readonly property string metaText: header.details.metaText || header.details.summary || ""
    // 24 above the cover, the cover, 24, the Play row, 24 below.
    implicitHeight: 24 + coverSize + 24 + playRow + 24

    // Soft shadow behind the cover, drawn by a rounded plate under it.
    Rectangle {
        x: cover.x
        y: cover.y
        width: cover.width
        height: cover.height
        radius: Theme.playlistCoverRadius
        color: Theme.surface
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: 0.5
            shadowBlur: 0.8
            shadowVerticalOffset: 8
        }
    }

    PlaylistCover {
        id: cover
        x: 24; y: 24
        width: header.coverSize; height: width
        source: header.details.coverUrl || ""
        covers: header.details.covers || []
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: coverMask
        }

        Rectangle {
            objectName: "playlistCoverHover"
            anchors.fill: parent
            color: "#73000000"
            visible: coverHit.containsMouse && header.editable
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
            enabled: header.editable
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: header.workspace.playlistModel.requestUI("cover", header.tab.ref, [])
        }
    }

    // Rounds the cover, its hover veil and the mosaic of four covers alike.
    Item {
        id: coverMask
        x: cover.x; y: cover.y
        width: cover.width; height: cover.height
        visible: false
        layer.enabled: true
        Rectangle {
            anchors.fill: parent
            radius: Theme.playlistCoverRadius
        }
    }

    Column {
        id: texts
        x: cover.x + cover.width + 24
        y: cover.y + cover.height - height
        width: header.width - x - 24
        spacing: 8

        Text {
            objectName: "playlistKind"
            text: "Playlist"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: Font.DemiBold
        }
        Text {
            objectName: "playlistTitleText"
            width: parent.width
            text: header.details.name || header.tab.title
            color: Theme.textPrimary
            font.family: Theme.displayFontFamily
            font.weight: Theme.displayFontWeight
            font.pixelSize: header.compact ? Theme.playlistTitleCompact : Theme.playlistTitleLarge
            font.letterSpacing: -0.02 * (header.compact ? Theme.playlistTitleCompact : Theme.playlistTitleLarge)
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.playlistTitleMin
            maximumLineCount: 1
            elide: Text.ElideRight
            MouseArea {
                anchors.fill: parent
                enabled: header.editable
                cursorShape: Qt.PointingHandCursor
                onClicked: header.workspace.playlistModel.requestUI("edit", header.tab.ref, [])
            }
        }
        Text {
            visible: text.length > 0
            width: parent.width
            text: header.details.description || ""
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
        Row {
            width: parent.width
            spacing: 6
            Text {
                id: creatorText
                text: header.workspace.playlistModel.creator
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.weight: Font.DemiBold
            }
            Text {
                text: "•"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Text {
                width: Math.max(0, parent.width - creatorText.width - 2 * parent.spacing - 12)
                text: header.metaText
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    Row {
        x: 24
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
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
}
