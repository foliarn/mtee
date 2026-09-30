import QtQuick
import Mtee

Item {
    id: art
    property string source: ""
    property var covers: []
    CoverArt {
        anchors.fill: parent
        source: art.source
        pattern: -1
        visible: art.source.length > 0 || art.covers.length === 0
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
