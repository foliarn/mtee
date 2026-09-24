import QtQuick

// Camelot key on its harmonic wheel colour; a missing key stays a dash.
Item {
    id: badge

    property string key: ""
    readonly property bool known: key.length > 1 && !isNaN(parseInt(key, 10))

    implicitWidth: known ? label.implicitWidth + 10 : dash.implicitWidth
    implicitHeight: 20

    Rectangle {
        visible: badge.known
        anchors.fill: parent
        radius: Theme.badgeRadius
        color: Theme.camelotColor(badge.key)

        Text {
            id: label
            anchors.centerIn: parent
            text: badge.key
            color: Theme.textOnColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeCaption
            font.weight: Font.DemiBold
        }
    }

    Text {
        id: dash
        visible: !badge.known
        anchors.verticalCenter: parent.verticalCenter
        text: "—"
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }
}
