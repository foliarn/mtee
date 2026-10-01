import QtQuick
import Mtee

// Placeholder for the artist: the raw artist tag and a note, nothing else. No link,
// no image, no action (plan 100, D1).
FullscreenCard {
    id: card

    required property var track

    objectName: "fullscreenArtistCard"
    heading: "Artist"

    Column {
        width: parent.width
        spacing: 8

        Text {
            objectName: "fullscreenArtistName"
            width: parent.width
            text: card.track.artist && card.track.artist.length > 0 ? card.track.artist : "Unknown artist"
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: 18
        }

        Text {
            text: "Artist details will come later."
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }
}
