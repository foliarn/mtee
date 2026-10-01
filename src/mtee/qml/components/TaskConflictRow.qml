import QtQuick
import Mtee

// One tag conflict listed like a changed file: the file, what differs, and small
// buttons to replace its tags or to dismiss it. Shared by the Tasks pane and page.
Column {
    id: conflictRow

    property string title: ""
    property string detail: ""
    property string stage: "pending"
    property string error: ""
    readonly property bool working: stage === "working"
    signal replaceRequested()
    signal dismissRequested()

    objectName: "tagConflictRow"
    spacing: 2

    Item {
        width: parent.width
        height: 24

        Icon {
            id: conflictIcon
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            name: "alert"
            size: 14
            color: conflictRow.error.length > 0 ? Theme.danger : Theme.textSecondary
        }

        Text {
            anchors.left: conflictIcon.right
            anchors.leftMargin: 6
            anchors.right: conflictButtons.left
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: conflictRow.title
            elide: Text.ElideMiddle
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            id: conflictButtons
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            IconButton {
                objectName: "replaceConflict"
                width: 22
                height: 22
                icon: "check"
                iconSize: 14
                enabledAction: !conflictRow.working
                tip: "Replace: delete the old tag values of this track and write the new ones"
                onClicked: conflictRow.replaceRequested()
            }

            IconButton {
                objectName: "dismissConflict"
                width: 22
                height: 22
                icon: "close"
                iconSize: 14
                enabledAction: !conflictRow.working
                tip: "Dismiss without writing"
                onClicked: conflictRow.dismissRequested()
            }
        }
    }

    Text {
        width: parent.width - 20
        x: 20
        text: conflictRow.detail
        wrapMode: Text.WordWrap
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Text {
        visible: conflictRow.working
        width: parent.width - 20
        x: 20
        text: "Replacing…"
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Text {
        visible: conflictRow.error.length > 0
        width: parent.width - 20
        x: 20
        text: conflictRow.error
        wrapMode: Text.WordWrap
        color: Theme.danger
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }
}
