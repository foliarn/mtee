import QtQuick
import Mtee

// A settings row: a label, a description and a number with minus and plus buttons.
// ``chosen`` carries the new value, already kept between ``from`` and ``to``.
Item {
    id: stepperRow

    property string label: ""
    property string description: ""
    property int value: 0
    property int from: 0
    property int to: 100
    property int step: 1
    signal chosen(int value)

    width: parent ? parent.width : 0
    height: Math.max(52, stepperTexts.implicitHeight + 16)

    Column {
        id: stepperTexts
        anchors.left: parent.left
        anchors.right: stepper.left
        anchors.rightMargin: 24
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            text: stepperRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: stepperRow.description
            wrapMode: Text.WordWrap
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Row {
        id: stepper
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 4

        TextButton {
            objectName: "stepDown"
            width: 32
            implicitHeight: 28
            text: "−"
            kind: "ghost"
            enabledAction: stepperRow.value > stepperRow.from
            onClicked: stepperRow.chosen(Math.max(stepperRow.from, stepperRow.value - stepperRow.step))
        }

        Text {
            objectName: "stepValue"
            width: 44
            height: 28
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: String(stepperRow.value)
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
            font.features: { "tnum": 1 }
        }

        TextButton {
            objectName: "stepUp"
            width: 32
            implicitHeight: 28
            text: "+"
            kind: "ghost"
            enabledAction: stepperRow.value < stepperRow.to
            onClicked: stepperRow.chosen(Math.min(stepperRow.to, stepperRow.value + stepperRow.step))
        }
    }
}
