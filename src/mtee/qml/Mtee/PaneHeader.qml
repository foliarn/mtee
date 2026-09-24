import QtQuick

// Title row of a sidebar pane, as in VS Code: uppercase caption and actions.
Item {
    id: header

    property string title: ""
    default property alias actions: actionRow.data

    implicitHeight: 36

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        text: header.title.toUpperCase()
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeCaption
        font.weight: Font.DemiBold
        font.letterSpacing: 1.1
    }

    Row {
        id: actionRow
        anchors.right: parent.right
        anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
    }
}
