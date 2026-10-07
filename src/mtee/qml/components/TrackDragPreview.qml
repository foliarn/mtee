import QtQuick
import Mtee

Rectangle {
    id: preview
    objectName: "trackDragPreview"
    property string trackTitle: ""
    property string artist: ""
    property int count: 1
    width: 290
    height: count > 1 ? 72 : 36
    color: Theme.surface
    border.width: 1
    border.color: Theme.separator
    z: 1000
    enabled: false
    Text {
        x: 12; width: parent.width - 24
        y: preview.count > 1 ? 9 : Math.round((preview.height - height) / 2)
        text: preview.trackTitle + " — " + (preview.artist || "Unknown artist")
        color: Theme.textPrimary; font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary; font.weight: Font.DemiBold
        elide: Text.ElideRight
    }
    Text {
        x: 12; y: 35; visible: preview.count > 1
        text: "and " + (preview.count - 1) + " other track" + (preview.count === 2 ? "" : "s") + "…"
        color: Theme.textSecondary; font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }
}
