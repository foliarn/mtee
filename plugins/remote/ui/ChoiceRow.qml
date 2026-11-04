import QtQuick
import Mtee

// A settings row with one choice among a few chips: the label and description of the rows of Mtee
// (ToggleRow, StepperRow) on the left, the chips on the right. ``options`` is a list of
// {key, label, name}; ``name`` is the objectName of the chip. ``chosen(key)`` carries the chip
// pressed; the page writes it and ``current`` follows the backend. When the row is too narrow for
// the chips beside the text (a split window, a small window), the chips go under the text.
Item {
    id: choiceRow

    property string label: ""
    property string description: ""
    property var options: []
    property string current: ""
    signal chosen(string key)

    // Room the text keeps next to the chips before they move under it.
    readonly property int textMinimum: 260
    readonly property bool stacked: width < chips.implicitWidth + textMinimum + 24

    width: parent ? parent.width : 0
    height: stacked ? texts.implicitHeight + chips.implicitHeight + 24
        : Math.max(52, texts.implicitHeight + 16)

    Column {
        id: texts
        x: 0
        y: choiceRow.stacked ? 8 : (choiceRow.height - implicitHeight) / 2
        width: choiceRow.stacked ? choiceRow.width : choiceRow.width - chips.implicitWidth - 24
        spacing: 2

        Text {
            text: choiceRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            visible: text.length > 0
            text: choiceRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Row {
        id: chips
        x: choiceRow.stacked ? 0 : choiceRow.width - implicitWidth
        y: choiceRow.stacked ? texts.y + texts.implicitHeight + 8
            : (choiceRow.height - implicitHeight) / 2
        spacing: 6

        Repeater {
            model: choiceRow.options

            delegate: FilterChip {
                required property var modelData
                objectName: modelData.name || ""
                text: modelData.label
                checked: choiceRow.current === modelData.key
                onToggled: choiceRow.chosen(modelData.key)
            }
        }
    }
}
