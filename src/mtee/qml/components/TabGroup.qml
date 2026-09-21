import QtQuick
import Mtee

Item {
    id: tabs

    property var labels: []
    property int currentIndex: 0
    signal selected(int index)
    signal closeRequested(int index)

    implicitHeight: 34

    Row {
        anchors.fill: parent
        spacing: Theme.spacingSmall

        Repeater {
            model: tabs.labels

            delegate: Rectangle {
                required property int index
                required property string modelData
                width: tabLabel.implicitWidth + closeMark.width + Theme.spacingLarge
                height: 32
                radius: Theme.controlRadius
                color: tabs.currentIndex === index ? Theme.activeSurface : "transparent"
                border.width: tabs.currentIndex === index ? 1 : 0
                border.color: Theme.border

                Text {
                    id: tabLabel
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spacing
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.modelData
                    color: tabs.currentIndex === index ? Theme.textPrimary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    id: closeMark
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spacingSmall
                    anchors.verticalCenter: parent.verticalCenter
                    text: "×"
                    color: Theme.textSecondary
                    font.pixelSize: 16
                    visible: tabs.labels.length > 1
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (mouse.x > closeMark.x) {
                            tabs.closeRequested(index)
                        } else {
                            tabs.currentIndex = index
                            tabs.selected(index)
                        }
                    }
                }
            }
        }

        ToolButton {
            text: "+"
            implicitWidth: 30
            onClicked: tabs.selected(tabs.currentIndex)
        }
    }
}
