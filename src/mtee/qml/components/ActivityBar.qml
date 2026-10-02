import QtQuick
import Mtee

// VS Code style activity bar. Each entry swaps the sidebar content; Settings
// opens an editor tab. Plugins and Profile are placeholders for later.
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
    // Running tasks plus tag conflicts waiting for the user, like the badge of a
    // source-control view.
    readonly property int runningTasks: {
        const waiting = workspace.tagConflicts && workspace.tagConflicts.count !== undefined
            ? workspace.tagConflicts.count : 0
        return jobsModel.runningCount + waiting
    }

    width: Theme.activityBarWidth
    color: Theme.chrome

    Column {
        anchors.top: parent.top
        width: parent.width

        ActivityButton { activity: "explorer"; icon: "explorer"; tip: "Explorer (Ctrl+Shift+E)" }
        ActivityButton { activity: "playlists"; icon: "playlists"; tip: "Playlists" }
        ActivityButton { activity: "artists"; icon: "artists"; tip: "Artist manager" }
        ActivityButton { activity: "convert"; icon: "convert"; tip: "Convert" }
        ActivityButton { activity: "tasks"; icon: "tasks"; tip: "Tasks"; badge: bar.runningTasks }
        ActivityButton { activity: "plugins"; icon: "plugins"; tip: "Plugins (coming later)" }
    }

    Column {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        width: parent.width

        ActivityButton { activity: "profile"; icon: "profile"; tip: "Profile (coming later)" }
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
