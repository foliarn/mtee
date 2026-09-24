import QtQuick
import QtQuick.Window

// Generated stand-in for embedded artwork: a flat colour and one shape per
// pattern index. Index -1 is a file without artwork.
Rectangle {
    id: cover

    property int pattern: -1
    property string source: ""
    readonly property int pixelSize: {
        const physical = Math.max(width, height) * Screen.devicePixelRatio
        const tiers = [64, 96, 128, 192, 256, 384, 512, 768, 1024]
        for (const tier of tiers) {
            if (tier >= physical)
                return tier
        }
        return 1024
    }
    readonly property var palettes: [
        ["#3B2A5E", "#FF5F7E"], ["#123C3A", "#7CF2C2"], ["#4A2A12", "#FFB347"],
        ["#1E2A4F", "#6FA8FF"], ["#2B2B2B", "#E9E9E9"], ["#4B1034", "#FF7AD1"],
        ["#2F3A12", "#D6F25F"], ["#10313F", "#48D1E8"]
    ]
    readonly property bool missing: pattern < 0 && source.length === 0
    readonly property var colours: {
        if (missing)
            return [Theme.selection, Theme.textMuted]
        const index = ((pattern % palettes.length) + palettes.length) % palettes.length
        return palettes[index]
    }
    readonly property int shape: missing ? -1 : pattern % 4

    color: colours[0]
    clip: true

    Image {
        objectName: "coverArtworkImage"
        anchors.fill: parent
        source: cover.source.length > 0
            ? cover.source.replace(/\/\d+$/, "") + "/" + cover.pixelSize : ""
        sourceSize: Qt.size(cover.pixelSize, cover.pixelSize)
        visible: cover.source.length > 0
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
    }

    Rectangle {
        visible: cover.source.length === 0 && cover.shape === 0
        width: cover.width * 0.56
        height: width
        radius: width / 2
        anchors.centerIn: parent
        color: cover.colours[1]
    }

    Rectangle {
        visible: cover.source.length === 0 && cover.shape === 1
        width: cover.width * 1.6
        height: cover.height * 0.22
        anchors.centerIn: parent
        rotation: -35
        antialiasing: true
        color: cover.colours[1]
    }

    Column {
        visible: cover.source.length === 0 && cover.shape === 2
        anchors.bottom: parent.bottom
        anchors.bottomMargin: cover.height * 0.14
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: cover.height * 0.08

        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: cover.width * (0.7 - index * 0.18)
                height: cover.height * 0.1
                anchors.horizontalCenter: parent.horizontalCenter
                color: cover.colours[1]
            }
        }
    }

    Rectangle {
        visible: cover.source.length === 0 && cover.shape === 3
        width: cover.width * 0.5
        height: width
        x: cover.width * 0.32
        y: cover.height * 0.14
        color: "transparent"
        border.width: Math.max(2, cover.width * 0.06)
        border.color: cover.colours[1]
    }

    Icon {
        visible: cover.missing
        anchors.centerIn: parent
        name: "music"
        size: Math.max(14, Math.round(cover.width * 0.42))
        color: Theme.textMuted
    }
}
