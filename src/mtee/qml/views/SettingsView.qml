import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Settings editor tab, as in VS Code. Only the player island switch acts on
// the prototype; the other entries show where future settings will live.
Rectangle {
    id: settings

    objectName: "settingsView"
    required property var workspace
    property int bottomInset: 0
    property bool rememberQueue: false

    color: Theme.editor

    Flickable {
        anchors.fill: parent
        contentHeight: content.implicitHeight + 48 + settings.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: content
            x: 24
            width: Math.min(720, settings.width - 48)
            spacing: 8

            Item { width: 1; height: 30 }

            SectionLabel { text: "Preferences" }

            Text {
                text: "Settings"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeHeading
                font.weight: Font.Bold
            }

            Item { width: 1; height: 16 }

            Group { title: "Playback" }

            ToggleRow {
                objectName: "islandSetting"
                label: "Show player island"
                description: "Floating player at the bottom of the editor while a track is loaded. Also in View › Player island."
                checked: settings.workspace.islandEnabled
                onToggled: (checked) => settings.workspace.setIslandEnabled(checked)
            }

            ToggleRow {
                label: "Remember the queue between sessions"
                description: "Restore the last queue and position when MTEE starts."
                checked: settings.rememberQueue
                onToggled: (checked) => settings.rememberQueue = checked
            }

            Group { title: "Library" }

            ValueRow { label: "Folders"; value: "Music"; action: "Add folder" }

            Group { title: "Appearance" }

            ValueRow { label: "Theme"; value: "Acid (dark)" }
            ValueRow { label: "Density"; value: "Comfortable" }

            Group { title: "Keyboard shortcuts" }

            Grid {
                width: parent.width
                columns: 2
                columnSpacing: 24
                rowSpacing: 10
                topPadding: 4

                Repeater {
                    model: [
                        "Play or pause", "Space",
                        "Play the selected track", "Enter or double-click",
                        "Edit info", "Ctrl+I",
                        "Select all", "Ctrl+A",
                        "Show Explorer", "Ctrl+Shift+E",
                        "Toggle sidebar", "Ctrl+B",
                        "Split editor", "Ctrl+\\",
                        "Fullscreen player", "F11",
                        "Next / previous track", "Ctrl+→ / Ctrl+←",
                        "Settings", "Ctrl+,"
                    ]
                    delegate: Text {
                        required property string modelData
                        required property int index
                        width: index % 2 === 0 ? 280 : implicitWidth
                        text: modelData
                        color: index % 2 === 0 ? Theme.textPrimary : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }
                }
            }
        }
    }

    component Group: Column {
        property string title: ""
        width: content.width
        topPadding: 20
        bottomPadding: 4
        spacing: 8

        Text {
            text: parent.title
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold
        }

        Rectangle { width: parent.width; height: 1; color: Theme.separator }
    }

    component ToggleRow: Item {
        id: toggleRow

        property string label: ""
        property string description: ""
        property bool checked: false
        signal toggled(bool checked)

        width: content.width
        height: Math.max(52, texts.implicitHeight + 16)

        Column {
            id: texts
            anchors.left: parent.left
            anchors.right: toggle.left
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: toggleRow.label
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                width: parent.width
                text: toggleRow.description
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        ToggleSwitch {
            id: toggle
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            checked: toggleRow.checked
            onToggled: (checked) => toggleRow.toggled(checked)
        }
    }

    component ValueRow: Item {
        id: valueRow

        property string label: ""
        property string value: ""
        property string action: ""

        width: content.width
        height: 44

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: valueRow.label
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: valueRow.value
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                visible: valueRow.action.length > 0
                implicitHeight: 28
                kind: "ghost"
                text: valueRow.action
                enabledAction: false
                tip: "Not available in the demo"
            }
        }
    }
}
