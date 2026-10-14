import QtQuick
import QtQuick.Effects
import Mtee

// Header of an artist page of the Artists view, laid out like the playlist page: a rounded
// cover (the artwork of the first track in album order), "Artist", the name in the display
// font, the track count and the credits the artist was cut from, then Play, Shuffle and the
// "…" menu. The menu holds the two credit actions of the core index; nothing else is edited.
Item {
    id: header

    required property var workspace
    required property var tab
    required property var trackModel
    readonly property bool compact: width < 800
    readonly property int coverSize: compact ? Theme.playlistCoverCompact : Theme.playlistCoverLarge
    readonly property int playRow: 56
    // Read again when the index is rebuilt: an action, a scan or a tag edit may change it.
    readonly property var info: { workspace.artistRevision; return workspace.artistInfo(tab.ref) }
    readonly property string coverSource: trackModel.count > 0 ? (trackModel.rows[0].coverUrl || "") : ""
    readonly property string fromText: info.oneArtistCredits.map(credit => "“" + credit + "”").join(", ")
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
        objectName: "artistCover"
        x: 24
        y: 24
        width: header.coverSize
        height: width
        source: header.coverSource
        covers: []
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: coverMask
        }
    }

    // Rounds the cover like the plate behind it.
    Item {
        id: coverMask
        x: cover.x
        y: cover.y
        width: cover.width
        height: cover.height
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
            objectName: "artistKind"
            text: "Artist"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: Font.DemiBold
        }

        Text {
            objectName: "artistTitleText"
            width: parent.width
            text: header.info.name || header.tab.title
            color: Theme.textPrimary
            font.family: Theme.displayFontFamily
            font.weight: Theme.displayFontWeight
            font.pixelSize: header.compact ? Theme.playlistTitleCompact : Theme.playlistTitleLarge
            font.letterSpacing: -0.02 * (header.compact ? Theme.playlistTitleCompact : Theme.playlistTitleLarge)
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.playlistTitleMin
            maximumLineCount: 1
            elide: Text.ElideRight
        }

        Text {
            objectName: "artistTrackCount"
            width: parent.width
            text: header.info.trackCount + (header.info.trackCount === 1 ? " track" : " tracks")
                + (header.fromText.length > 0 ? "  ·  from " + header.fromText : "")
            elide: Text.ElideRight
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }

    Row {
        x: 24
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        spacing: 16

        IconButton {
            objectName: "artistPlay"
            width: 56
            height: 56
            icon: "play"
            iconSize: 24
            iconColor: Theme.editor
            color: Theme.primary
            radius: width / 2
            hoverColor: Theme.editor
            tip: "Play the tracks of this artist"
            onClicked: header.workspace.playArtistRows(header.tab.ref, header.trackModel.rows, false)
        }

        IconButton {
            objectName: "artistShuffle"
            width: 56
            height: 56
            radius: width / 2
            icon: "shuffle"
            iconSize: 24
            tip: "Shuffle the tracks of this artist"
            onClicked: header.workspace.playArtistRows(header.tab.ref, header.trackModel.rows, true)
        }

        IconButton {
            id: moreButton
            objectName: "artistMoreButton"
            width: 56
            height: 56
            radius: width / 2
            icon: "more"
            iconSize: 24
            tip: "More actions for this artist"
            onClicked: artistMenu.popup(moreButton, 0, moreButton.height)
        }
    }

    AppMenu {
        id: artistMenu
        objectName: "artistActionsMenu"

        AppMenuItem {
            objectName: "thisIsOneArtist"
            text: "This is one artist"
            enabled: header.info.oneArtistCredits.length > 0
            onTriggered: header.workspace.makeArtistOneArtist(header.tab.ref)
        }
        AppMenuItem {
            objectName: "splitArtists"
            text: "Split into separate artists"
            enabled: header.info.splitCredits.length > 0
            onTriggered: header.workspace.splitArtist(header.tab.ref)
        }
    }
}
