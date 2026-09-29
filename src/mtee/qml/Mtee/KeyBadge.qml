import QtQuick

// Key on its Camelot wheel colour, written in the notation the user chose. A key
// that is not a known key is shown as plain text; a missing key stays a dash.
Item {
    id: badge

    property string key: ""
    // Camelot code that gives the colour, whatever notation ``key`` is written in.
    property string camelot: ""
    readonly property bool known: camelot.length > 1 && !isNaN(parseInt(camelot, 10))

    implicitWidth: known ? label.implicitWidth + 10 : plain.implicitWidth
    implicitHeight: 20

    Rectangle {
        visible: badge.known
        anchors.fill: parent
        radius: Theme.badgeRadius
        color: Theme.camelotColor(badge.camelot)

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
        id: plain
        visible: !badge.known
        anchors.verticalCenter: parent.verticalCenter
        text: badge.key.length > 0 ? badge.key : "—"
        color: badge.key.length > 0 ? Theme.textSecondary : Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }
}
