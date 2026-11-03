import QtQuick
import QtQuick.Controls.Basic

// A search control that folds into an icon (plan 130): the icon opens a field, Esc clears the
// text and folds it again. ``text`` is the text shown; ``edited`` carries what the user typed.
// ``fieldObjectName`` and ``buttonObjectName`` name the inner field and icon for tests.
Row {
    id: search

    property string text: ""
    property string placeholder: "Search"
    property string tip: "Search"
    property bool open: false
    property int expandedWidth: 220
    property string fieldObjectName: ""
    property string buttonObjectName: ""
    readonly property bool fieldActive: field.activeFocus
    readonly property alias field: field
    signal edited(string text)

    spacing: 2

    function openField() {
        open = true
        field.forceActiveFocus()
    }

    function clear() {
        field.text = ""
        search.edited("")
        open = false
    }

    TextField {
        id: field
        objectName: search.fieldObjectName
        width: search.open ? search.expandedWidth : 0
        height: 28
        anchors.verticalCenter: parent.verticalCenter
        opacity: search.open ? 1 : 0
        clip: true
        selectByMouse: true
        placeholderText: search.placeholder
        text: search.text
        color: Theme.textPrimary
        placeholderTextColor: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
        onTextEdited: search.edited(text)
        Keys.onEscapePressed: (event) => {
            search.clear()
            event.accepted = true
        }
        Behavior on width { NumberAnimation { duration: 190; easing.type: Easing.OutExpo } }
        background: Rectangle {
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: field.activeFocus ? Theme.focus : Theme.separator
        }
    }

    IconButton {
        objectName: search.buttonObjectName
        icon: "search"
        iconSize: 18
        tip: search.tip
        active: search.open || field.text.length > 0
        onClicked: {
            search.open = !search.open
            if (search.open)
                field.forceActiveFocus()
        }
    }
}
