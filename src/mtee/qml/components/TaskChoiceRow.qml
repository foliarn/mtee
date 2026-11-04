import QtQuick
import Mtee

// One item that waits for the user, listed like a tag conflict (TaskConflictRow): the item,
// what is needed, one small button to answer and one cross to dismiss. The wording comes from
// the caller (a plugin's WaitingItems). Shared by the notifications bell.
Column {
    id: choiceRow

    property string title: ""
    property string detail: ""
    property string actionText: "Open"
    signal chosen()
    signal dismissRequested()

    objectName: "taskChoiceRow"
    spacing: 2

    Item {
        width: parent.width
        height: 26

        Icon {
            id: choiceIcon
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            name: "alert"
            size: 14
            color: Theme.textSecondary
        }

        Text {
            anchors.left: choiceIcon.right
            anchors.leftMargin: 6
            anchors.right: choiceButtons.left
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: choiceRow.title
            elide: Text.ElideMiddle
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            id: choiceButtons
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            IconButton {
                objectName: "dismissWaiting"
                anchors.verticalCenter: parent.verticalCenter
                width: 22
                height: 22
                icon: "close"
                iconSize: 14
                tip: "Dismiss"
                onClicked: choiceRow.dismissRequested()
            }
        }
    }

    Text {
        width: parent.width - 20
        x: 20
        text: choiceRow.detail
        wrapMode: Text.WordWrap
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    TextButton {
        objectName: "answerWaiting"
        x: 20
        text: choiceRow.actionText
        kind: "ghost"
        implicitHeight: 24
        onClicked: choiceRow.chosen()
    }
}
