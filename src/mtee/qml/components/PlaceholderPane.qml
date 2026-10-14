import QtQuick
import Mtee

// Reserved activity: the button exists, the feature does not yet.
Item {
    id: pane

    property string title: ""
    property string icon: ""
    property string message: ""

    objectName: "placeholderPane"

    PaneHeader {
        id: header
        width: parent.width
        title: pane.title
    }

    Column {
        anchors.top: header.bottom
        anchors.topMargin: 48
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width - 48
        spacing: 12

        Icon {
            anchors.horizontalCenter: parent.horizontalCenter
            name: pane.icon
            size: 40
            color: Theme.textMuted
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Coming later"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            font.weight: Font.DemiBold
        }

        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: pane.message
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
