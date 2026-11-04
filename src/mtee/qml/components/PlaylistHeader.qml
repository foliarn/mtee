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
    // A tab of a plugin lists its rows like a playlist; the plugin describes the header.
    readonly property var pluginUi: workspace.pluginUi || null
    readonly property bool pluginTab: pluginUi !== null && pluginUi.isTrackList(tab.kind)
    readonly property var details: {
        workspace.revision
        return pluginTab ? pluginUi.tabHeader(tab.kind, tab.ref, pluginUi.revision) : workspace.playlistModel.details(tab.ref)
    }
    // Buttons that plugins add beside Play and Shuffle, for this tab kind (or local playlists).
    readonly property var pluginActions: pluginUi !== null
        ? pluginUi.headerActions(tab.kind, tab.ref, pluginUi.revision) : []
    readonly property bool compact: width < 800
    readonly property int coverSize: compact ? Theme.playlistCoverCompact : Theme.playlistCoverLarge
    readonly property int playRow: 56
    readonly property bool editable: tab.ref !== "liked" && !pluginTab
    // What plugins add to the meta line of a local playlist ("linked to Spotify").
    readonly property string pluginMeta: pluginUi !== null && !pluginTab
        ? pluginUi.playlistMeta(tab.ref, pluginUi.revision) : ""
    readonly property string baseMeta: header.details.metaText || header.details.summary || ""
    // "· N hidden" when the track filter leaves tracks out of this list (plan 125.3).
    readonly property string hiddenText: (trackModel.hiddenCount || 0) > 0
        ? trackModel.hiddenCount + " hidden" : ""
    readonly property string metaText: [baseMeta, pluginMeta, hiddenText]
        .filter(part => part.length > 0).join(" · ")
    // 24 above the cover, the cover, 24, the Play row, 24 below.
    implicitHeight: 24 + coverSize + 24 + playRow + 24

    // Play and Shuffle skip the rows without a local file, in a local playlist and in a plugin list.
    function play(shuffled) {
        if (pluginTab)
            workspace.playPluginRows(tab.kind, tab.ref, trackModel.rows, shuffled)
        else
            workspace.playPlaylistRows(tab.ref, trackModel.rows, shuffled)
    }

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
        objectName: "playlistCover"
        x: 24; y: 24
        width: header.coverSize; height: width
        source: header.details.coverUrl || ""
        covers: header.details.covers || []
        heart: header.tab.ref === "liked"
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
            text: header.pluginTab ? header.details.kindLabel : "Playlist"
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
                visible: text.length > 0
                text: header.pluginTab ? (header.details.creator || "") : header.workspace.playlistModel.creator
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.weight: Font.DemiBold
            }
            Text {
                visible: creatorText.visible
                text: "•"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Text {
                width: Math.max(0, parent.width - (creatorText.visible ? creatorText.width + 2 * parent.spacing + 12 : 0))
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
            onClicked: header.play(false)
        }
        IconButton {
            objectName: "playlistShuffle"
            anchors.verticalCenter: parent.verticalCenter
            icon: "shuffle"; iconSize: 24; tip: "Shuffle visible tracks"
            onClicked: header.play(true)
        }
        Repeater {
            model: header.pluginActions
            delegate: Loader {
                required property var modelData
                anchors.verticalCenter: parent.verticalCenter
                sourceComponent: modelData.kind === "toggle" ? chipAction : buttonAction

                Component {
                    id: buttonAction
                    TextButton {
                        objectName: "pluginHeaderAction_" + modelData.id
                        text: modelData.label
                        icon: modelData.icon
                        kind: modelData.kind
                        enabledAction: modelData.enabled
                        tip: modelData.enabled ? "" : (modelData.reason || "")
                        onClicked: header.pluginUi.runHeaderAction(modelData.id, header.tab.ref)
                    }
                }
                Component {
                    id: chipAction
                    FilterChip {
                        objectName: "pluginHeaderAction_" + modelData.id
                        implicitHeight: 32
                        text: modelData.label
                        checked: modelData.checked
                        onToggled: header.pluginUi.runHeaderAction(modelData.id, header.tab.ref)
                    }
                }
            }
        }
    }
}
