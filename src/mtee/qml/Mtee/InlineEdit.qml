import QtQuick
import QtQuick.Controls.Basic

// A text field that replaces a label in place, for renames (plan 130). Call ``begin(value)`` to
// show it. Enter commits, Esc cancels; an empty or unchanged text cancels too. With
// ``keepExtension`` the part after the last dot is not selected when editing starts.
TextField {
    id: edit

    property string original: ""
    property bool keepExtension: false
    readonly property int extensionStart: {
        const dot = original.lastIndexOf(".")
        return keepExtension && dot > 0 ? dot : original.length
    }
    signal committed(string text)
    signal cancelled()

    function begin(value) {
        original = value
        text = value
        visible = true
        forceActiveFocus()
        select(0, extensionStart)
    }

    function finish(accept) {
        if (!visible)
            return
        visible = false
        const value = text.trim()
        if (!accept || value.length === 0 || value === original) {
            cancelled()
            return
        }
        committed(value)
    }

    visible: false
    height: 28
    selectByMouse: true
    color: Theme.textPrimary
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSizeSecondary
    onAccepted: finish(true)
    Keys.onEscapePressed: (event) => {
        finish(false)
        event.accepted = true
    }
    onActiveFocusChanged: if (!activeFocus && visible) finish(true)
    background: Rectangle {
        radius: Theme.radiusChip
        color: Theme.chrome
        border.width: 1
        border.color: Theme.focus
    }
}
