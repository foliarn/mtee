import QtQuick
import Mtee

// A notice on a page: a surface card with a bar in the warning colour on the left, like a notification card
// of the notifications bell.
Rectangle {
    id: notice

    property string title: ""
    property string text: ""

    width: parent ? parent.width : 0
    height: noticeBody.implicitHeight + 20
    color: Theme.surface
    radius: Theme.radius

    Rectangle {
        width: 3
        height: parent.height
        radius: 2
        color: Theme.warning
    }

    Column {
        id: noticeBody
        x: 14
        y: 10
        width: parent.width - 28
        spacing: 3

        Text {
            width: parent.width
            text: notice.title
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Text {
            width: parent.width
            text: notice.text
            wrapMode: Text.WordWrap
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
