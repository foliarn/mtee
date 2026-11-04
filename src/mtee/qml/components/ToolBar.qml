import QtQuick
import Mtee

// One of the two tool bars of the frame (plan 131.5): a column of header-sized buttons built from the
// tool window registry for this side, the top group first and the bottom group at the foot. A click
// toggles the window in its dock; Shift+click stacks it below the window already shown; a right click
// offers "Open below" and "Close". The Tasks badge counts the running jobs and what waits for the user.
Item {
    id: bar

    required property var workspace
    // "left" or "right": the bar shows the registry entries of this side.
    required property string side

    // Bumped on every layout change, so the active state of each button is read again.
    property int layoutRevision: 0
    readonly property string activeTabKind: (workspace.activeTabId || "").split(":")[0]
    readonly property var entries: workspace.toolWindows ? workspace.toolWindows.entries : []
    readonly property var topEntries: entries.filter(entry => entry.side === side && entry.place === "top")
    readonly property var bottomEntries: entries.filter(entry => entry.side === side && entry.place === "bottom")
    // Running tasks plus what waits for the user (tag conflicts and the items plugins list under
    // "Waiting for you"), like the badge of a source-control view.
    readonly property int runningTasks: {
        const conflicts = workspace.tagConflicts && workspace.tagConflicts.count !== undefined
            ? workspace.tagConflicts.count : 0
        const waiting = workspace.pluginUi ? workspace.pluginUi.waitingCount : 0
        return jobsModel.runningCount + conflicts + waiting
    }

    width: Theme.frameSize

    Connections {
        target: bar.workspace
        function onLayoutChanged() { bar.layoutRevision++ }
    }

    // Whether the window is shown in its dock now.
    function shown(entry) {
        layoutRevision
        if (entry.kind !== "window" || workspace.fullscreen)
            return false
        const dock = workspace.dockState(entry.side)
        return dock.open === true && dock.windows.indexOf(entry.id) >= 0
    }

    function badgeOf(entry) {
        if (entry.id === "tasks")
            return runningTasks
        if (entry.owner.length > 0 && workspace.pluginUi)
            return workspace.pluginUi.activityBadge(entry.id, workspace.pluginUi.revision)
        return 0
    }

    function activate(entry, below) {
        if (entry.kind === "action") {
            if (entry.id === "settings")
                workspace.openSettings()
            return
        }
        if (below)
            workspace.openToolWindow(entry.id, true)
        else
            workspace.toggleToolWindow(entry.id)
    }

    AppMenu {
        id: entryMenu
        property var entry: null

        AppMenuItem {
            text: "Open below"
            onTriggered: bar.workspace.openToolWindow(entryMenu.entry.id, true)
        }
        AppMenuItem {
            text: "Close"
            enabled: entryMenu.entry !== null && bar.shown(entryMenu.entry)
            onTriggered: bar.workspace.closeToolWindow(entryMenu.entry.id)
        }
    }

    Column {
        id: topColumn
        anchors.top: parent.top
        width: parent.width

        Repeater {
            model: bar.topEntries
            delegate: BarEntry {
                required property var modelData
                entry: modelData
            }
        }
    }

    Column {
        id: bottomColumn
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        width: parent.width

        Repeater {
            model: bar.bottomEntries
            delegate: BarEntry {
                required property var modelData
                entry: modelData
            }
        }
    }

    component BarEntry: HeaderButton {
        id: button

        required property var entry

        objectName: "activity-" + entry.id
        icon: entry.icon
        iconSize: 20
        tip: entry.shortcut.length > 0 ? entry.tip + " (" + entry.shortcut + ")" : entry.tip
        badge: bar.badgeOf(entry)
        active: entry.kind === "action"
            ? bar.activeTabKind === "settings" && !bar.workspace.fullscreen
            : bar.shown(entry)
        onClicked: bar.activate(entry, (button.lastModifiers & Qt.ShiftModifier) !== 0)

        // Right clicks reach this area because the button takes only left clicks.
        MouseArea {
            z: -1
            anchors.fill: parent
            acceptedButtons: Qt.RightButton
            onClicked: {
                if (button.entry.kind !== "window")
                    return
                entryMenu.entry = button.entry
                entryMenu.popup(button, 0, button.height)
            }
        }
    }
}
