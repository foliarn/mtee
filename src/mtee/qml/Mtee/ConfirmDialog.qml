import QtQuick
import QtQuick.Controls.Basic

// A modal question with up to three buttons (plan 130). A button is {key, label, kind} with kind
// primary, ghost or danger. ``answered`` carries the key of the button pressed, or "cancel" for
// Esc or when the popup closes otherwise. Extra content (a field) goes in as children. Same
// surface as the plugin dialogs: radius 8, 20 px padding.
Popup {
    id: dialog

    property string title: ""
    property string text: ""
    property var buttons: [{ "key": "ok", "label": "OK", "kind": "primary" }]
    property int dialogWidth: 420
    default property alias extra: extraItems.data
    property bool answeredAlready: false
    signal answered(string key)

    parent: Overlay.overlay
    width: Math.min(dialogWidth, parent ? parent.width - 32 : dialogWidth)
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? Math.max(16, (parent.height - height) / 2) : 0
    modal: true
    focus: true
    padding: 20
    closePolicy: Popup.CloseOnEscape

    function answer(key) {
        answeredAlready = true
        dialog.close()
        dialog.answered(key)
    }

    onOpened: answeredAlready = false
    onClosed: {
        if (!answeredAlready)
            dialog.answered("cancel")
        answeredAlready = true
    }

    background: Rectangle {
        color: Theme.surface
        radius: Theme.radiusWindow
        border.width: 1
        border.color: Theme.separator
    }

    contentItem: Column {
        spacing: 12

        Text {
            width: parent.width
            text: dialog.title
            visible: text.length > 0
            wrapMode: Text.WordWrap
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold
        }
        Text {
            width: parent.width
            text: dialog.text
            visible: text.length > 0
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
        Column {
            id: extraItems
            width: parent.width
            spacing: 8
        }
        Row {
            objectName: "confirmButtons"
            anchors.right: parent.right
            spacing: 8

            Repeater {
                model: dialog.buttons
                delegate: Loader {
                    id: slot
                    required property var modelData
                    sourceComponent: modelData.kind === "danger" ? dangerComponent : textComponent

                    Component {
                        id: textComponent
                        TextButton {
                            objectName: "confirmButton_" + slot.modelData.key
                            text: slot.modelData.label
                            kind: slot.modelData.kind === "primary" ? "primary" : "ghost"
                            onClicked: dialog.answer(slot.modelData.key)
                        }
                    }
                    Component {
                        id: dangerComponent
                        DangerButton {
                            objectName: "confirmButton_" + slot.modelData.key
                            text: slot.modelData.label
                            onClicked: dialog.answer(slot.modelData.key)
                        }
                    }
                }
            }
        }
    }
}
