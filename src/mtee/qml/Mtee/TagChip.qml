import QtQuick

// A small rounded label (plan 130). ``tone`` is neutral, primary or warning.
Rectangle {
    id: chip

    property string text: ""
    property string tone: "neutral"
    readonly property color toneColor: tone === "primary" ? Theme.primary
        : tone === "warning" ? Theme.warning : Theme.textSecondary

    implicitWidth: label.implicitWidth + 12
    implicitHeight: 18
    radius: Theme.radiusChip
    color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.14)
    border.width: 1
    border.color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.4)

    Text {
        id: label
        anchors.centerIn: parent
        text: chip.text
        color: chip.toneColor
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeCaption
        font.weight: Font.DemiBold
    }
}
