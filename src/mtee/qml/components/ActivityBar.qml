import QtQuick
import Mtee

// VS Code style activity bar. Each entry swaps the sidebar content; Settings
// opens an editor tab. Profile is a placeholder for later. Plugins appear only when
// the build enables them (v0.1 does not). Artists lists the core artist index.
Rectangle {
    id: bar

    required property var workspace
    readonly property string activeTabKind: {
        const groups = workspace.groups
        if (groups.length === 0)
            return ""
        const active = groups[workspace.activeGroup].active
        return active.split(":")[0]
    }
    // Running tasks plus what waits for the user (tag conflicts and the items plugins list
    // under "Waiting for you"), like the badge of a source-control view.
    readonly property int runningTasks: {
        const conflicts = workspace.tagConflicts && workspace.tagConflicts.count !== undefined
            ? workspace.tagConflicts.count : 0
        const waiting = workspace.pluginUi ? workspace.pluginUi.waitingCount : 0
        return jobsModel.runningCount + conflicts + waiting
    }

    width: Theme.activityBarWidth
    color: Theme.chrome

    Column {
        anchors.top: parent.top
        width: parent.width

        ActivityButton { activity: "explorer"; icon: "explorer"; tip: "Explorer (Ctrl+Shift+E)" }
        ActivityButton { activity: "playlists"; icon: "playlists"; tip: "Playlists" }
        ActivityButton {
            visible: bar.workspace.pluginUiEnabled
            activity: "convert"; icon: "convert"; tip: "Convert"
        }
        ActivityButton { activity: "tasks"; icon: "tasks"; tip: "Tasks"; badge: bar.runningTasks }
        ActivityButton { activity: "artists"; icon: "artists"; tip: "Artists" }
        // The activities that plugins own: none without a plugin.
        Repeater {
            model: bar.workspace.pluginUi ? bar.workspace.pluginUi.activities : []
            delegate: ActivityButton {
                required property var modelData
                activity: modelData.id; icon: modelData.icon; tip: modelData.tip
            }
        }
        ActivityButton {
            activity: "plugins"
            icon: "plugins"
            tip: "Plugins"
        }
    }

    Column {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        width: parent.width

        // The Profile page is a tab of the editor, not a sidebar activity.
        ActivityButton {
            objectName: "activity-profile"
            activity: ""
            icon: "profile"
            tip: "Profile"
            highlighted: bar.activeTabKind === "profile" && !bar.workspace.fullscreen
            onClicked: bar.workspace.openProfile()
        }
        ActivityButton {
            activity: ""
            icon: "settings"
            tip: "Settings (Ctrl+,)"
            highlighted: bar.activeTabKind === "settings" && !bar.workspace.fullscreen
            onClicked: bar.workspace.openSettings()
        }
    }

    component ActivityButton: Item {
        id: button

        property string activity: ""
        property string icon: ""
        property string tip: ""
        property int badge: 0
        property bool highlighted: activity.length > 0 && bar.workspace.activity === activity
            && bar.workspace.sidebarVisible && !bar.workspace.fullscreen
        signal clicked()

        objectName: "activity-" + (activity || icon)
        width: Theme.activityBarWidth
        height: Theme.activityBarWidth

        Rectangle {
            visible: button.highlighted
            width: 2
            height: parent.height
            color: Theme.primary
        }

        Icon {
            anchors.centerIn: parent
            name: button.icon
            size: 24
            color: button.highlighted || mouse.containsMouse ? Theme.textPrimary : Theme.textMuted
        }

        Rectangle {
            visible: button.badge > 0
            x: parent.width - 20
            y: parent.height - 22
            width: Math.max(14, badgeText.implicitWidth + 6)
            height: 14
            color: Theme.primary

            Text {
                id: badgeText
                anchors.centerIn: parent
                text: button.badge
                color: Theme.textOnColor
                font.family: Theme.fontFamily
                font.pixelSize: 10
                font.weight: Font.Bold
            }
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: {
                if (button.activity.length > 0)
                    bar.workspace.setActivity(button.activity)
                button.clicked()
            }
        }

        HoverTip {
            visible: mouse.containsMouse
            text: button.tip
        }
    }
}
