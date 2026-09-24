import QtQuick
import Mtee

// Right panel with two tabs: Info follows the selection, Queue the playback.
Rectangle {
    id: panel

    required property var workspace
    property int bottomInset: 0
    signal resizeRequested(real delta)

    objectName: "rightPanel"
    color: Theme.sidebar

    Rectangle {
        width: 1
        height: parent.height
        color: Theme.separator
        opacity: 0.6
    }

    Item {
        id: header
        x: 1
        width: parent.width - 1
        height: Theme.tabHeight

        Row {
            x: 10
            height: parent.height

            Repeater {
                model: [{ "key": "info", "label": "Info" }, { "key": "queue", "label": "Queue" }]

                delegate: Item {
                    id: tabItem
                    required property var modelData
                    readonly property bool current: panel.workspace.rightPanelTab === modelData.key

                    width: tabLabel.implicitWidth + 20
                    height: header.height

                    Text {
                        id: tabLabel
                        anchors.centerIn: parent
                        text: tabItem.modelData.label.toUpperCase()
                        color: tabItem.current || tabMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.1
                    }

                    Rectangle {
                        visible: tabItem.current
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: tabLabel.implicitWidth
                        height: 2
                        color: Theme.primary
                    }

                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: panel.workspace.showRightPanel(tabItem.modelData.key)
                    }
                }
            }
        }

        IconButton {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 26
            height: 26
            icon: "close"
            iconSize: 16
            tip: "Close panel"
            onClicked: panel.workspace.setRightPanelVisible(false)
        }
    }

    Loader {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.leftMargin: 1
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        sourceComponent: panel.workspace.rightPanelTab === "queue" ? queueComponent : infoComponent
    }

    Component { id: infoComponent; InfoPanel { workspace: panel.workspace } }
    Component { id: queueComponent; QueuePanel { workspace: panel.workspace; bottomInset: panel.bottomInset } }

    MouseArea {
        property real pressX: 0
        anchors.left: parent.left
        anchors.leftMargin: -3
        width: 6
        height: parent.height
        cursorShape: Qt.SizeHorCursor
        onPressed: (event) => pressX = event.x
        onPositionChanged: (event) => { if (pressed) panel.resizeRequested(pressX - event.x) }
    }
}
