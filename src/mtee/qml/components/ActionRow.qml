import QtQuick
import Mtee

// A settings row: a label, a description and one action button on the right. ``detail`` adds a
// line under the description; ``code`` shows a code badge left of the button; ``actionKind`` is
// a TextButton kind (ghost, primary...); ``danger`` draws the button as a DangerButton.
Item {
    id: actionRow

    property string label: ""
    property string description: ""
    property string detail: ""
    property string actionText: ""
    property string actionKind: "ghost"
    property string code: ""
    property bool enabledAction: true
    property bool danger: false
    signal action()

    width: parent ? parent.width : 0
    height: Math.max(60, actionTexts.implicitHeight + 16)

    Column {
        id: actionTexts
        anchors.left: parent.left
        anchors.right: actionCode.visible ? actionCode.left : actionButton.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: actionRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: actionRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Text {
            visible: actionRow.detail.length > 0
            width: parent.width
            text: actionRow.detail
            wrapMode: Text.WordWrap
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            topPadding: 4
        }
    }

    CodeBadge {
        id: actionCode
        visible: actionRow.code.length > 0
        anchors.right: actionButton.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        text: actionRow.code
    }

    Loader {
        id: actionButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        sourceComponent: actionRow.danger ? dangerAction : plainAction
    }

    Component {
        id: plainAction

        TextButton {
            objectName: "action_" + actionRow.objectName
            implicitHeight: 28
            kind: actionRow.actionKind
            text: actionRow.actionText
            enabledAction: actionRow.enabledAction
            onClicked: actionRow.action()
        }
    }

    Component {
        id: dangerAction

        DangerButton {
            objectName: "action_" + actionRow.objectName
            text: actionRow.actionText
            enabledAction: actionRow.enabledAction
            onClicked: actionRow.action()
        }
    }
}
