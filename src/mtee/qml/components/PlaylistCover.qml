import QtQuick
import Mtee

Item {
    id: art
    property string source: ""
    property var covers: []
    // Liked tracks without a cover of its own: the accent gradient and a heart.
    property bool heart: false
    CoverArt {
        anchors.fill: parent
        source: art.source
        pattern: -1
        visible: art.source.length > 0 || (art.covers.length === 0 && !art.heart)
    }
    Rectangle {
        objectName: "playlistCoverHeart"
        anchors.fill: parent
        visible: art.heart && art.source.length === 0
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.primary }
            GradientStop { position: 1; color: Qt.darker(Theme.primary, 1.45) }
        }
        Icon {
            anchors.centerIn: parent
            name: "heart"
            size: Math.round(art.width * 0.42)
            color: Theme.editor
        }
    }
    Grid {
        anchors.fill: parent
        columns: 2
        visible: art.source.length === 0 && art.covers.length > 0
        Repeater {
            model: 4
            CoverArt {
                required property int index
                width: art.width / 2
                height: art.height / 2
                source: art.covers.length ? (art.covers[index % art.covers.length] || "") : ""
                pattern: -1
            }
        }
    }
}
