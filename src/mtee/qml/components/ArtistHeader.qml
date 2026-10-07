import QtQuick
import QtQuick.Effects
import Mtee

// Header of an artist page, laid out like the playlist page: a rounded placeholder
// cover with its soft shadow, "Artist", the name in the display font, the number of
// tracks, then Play and Shuffle. There is no description, creator or cover editing.
Item {
    id: header

    required property var workspace
    required property var tab
    required property var trackModel
    readonly property bool compact: width < 800
    readonly property int coverSize: compact ? Theme.playlistCoverCompact : Theme.playlistCoverLarge
    readonly property int playRow: 56
    readonly property int trackCount: trackModel.count
    readonly property var manager: workspace.artistManager
    property var profile: ({ "roles": [], "bassRelated": null, "tags": [], "hidden": false })
    readonly property string profileSummary: {
        const parts = profile.roles.concat(profile.bassRelated === true ? ["Bass-related"] : [],
                                           profile.tags, profile.hidden ? ["idgaf"] : [])
        return parts.length > 0 ? parts.join(" · ") : "No type yet"
    }

    function reloadProfile() {
        if (manager && manager.available)
            profile = manager.artistProfile(tab.ref)
    }

    Component.onCompleted: reloadProfile()

    Connections {
        target: header.manager && header.manager.available ? header.manager : null
        function onArtistProfileChanged(artistId) {
            if (artistId === header.tab.ref)
                header.reloadProfile()
        }
    }
    // 24 above the cover, the cover, 24, the Play row, 24 below.
    implicitHeight: 24 + coverSize + 24 + playRow + 24

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
        source: ""
        covers: []
        layer.enabled: true
        layer.effect: MultiEffect {
            maskEnabled: true
            maskSource: coverMask
        }
    }

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
            text: "Artist"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: Font.DemiBold
        }

        Text {
            objectName: "artistTitleText"
            width: parent.width
            text: header.tab.title
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
            text: header.trackCount + (header.trackCount === 1 ? " track" : " tracks")
            elide: Text.ElideRight
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            objectName: "artistProfileSummary"
            width: parent.width
            text: header.profileSummary
            elide: Text.ElideRight
            color: header.profile.hidden ? Theme.textMuted : Theme.textSecondary
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
            anchors.verticalCenter: parent.verticalCenter
            icon: "shuffle"
            iconSize: 24
            tip: "Shuffle the tracks of this artist"
            onClicked: header.workspace.playArtistRows(header.tab.ref, header.trackModel.rows, true)
        }

        TextButton {
            objectName: "artistEditProfile"
            anchors.verticalCenter: parent.verticalCenter
            text: "Edit profile"
            kind: "ghost"
            onClicked: profileDialog.show(header.tab.ref, header.tab.title)
        }
    }

    ArtistProfileDialog {
        id: profileDialog
        manager: header.manager
        parent: Overlay.overlay
    }
}
