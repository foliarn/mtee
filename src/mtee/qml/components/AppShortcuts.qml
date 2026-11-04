import QtQuick
import Mtee

// The window shortcuts (plan 131.10, decision P4), loaded by Main.qml. They are off while a text field
// has the focus, except the ones that never checked it: F11, the fullscreen page keys, Ctrl+Z and Ctrl+W
// keep their behaviour. Each shortcut that depends on a window or a dock reads the state when it fires.
// The list of the shortcuts shown to the user is the Keyboard shortcuts page of Settings: keep both in step.
Item {
    id: keys

    required property var window
    required property var workspace

    // Bumped on every layout change, so the dock rules are read again.
    property int dockRevision: 0
    Connections {
        target: keys.workspace
        function onLayoutChanged() { keys.dockRevision++ }
    }

    readonly property var toolEntries: workspace.toolWindows ? workspace.toolWindows.entries : []
    readonly property bool overlayDocks: window.width < Theme.overlayDockWidth

    // The queue list of the fullscreen player keeps its own arrow keys.
    function queueListFocused() {
        const focused = window.activeFocusItem
        return focused !== null && focused !== undefined && focused.objectName === "fullscreenQueueList"
    }

    function textInputFocused() {
        const focused = window.activeFocusItem
        return focused !== null && focused !== undefined
            && (focused.objectName === "folderSearchField"
                || focused.objectName === "fieldEditorInput"
                || focused instanceof TextInput
                || focused instanceof TextEdit)
    }

    function explorerShown() {
        keys.dockRevision
        const left = keys.workspace.dockState("left")
        return left.open === true && left.windows.indexOf("explorer") >= 0
    }

    function dockOpen(side) {
        keys.dockRevision
        return keys.workspace.dockState(side).open === true
    }

    function hasActiveTab() {
        return keys.workspace.activeTabId.length > 0
    }

    // The tool window bound to ``shortcut`` (Alt+1 to Alt+5 in the registry), or null.
    function toolWindowFor(shortcut) {
        for (const entry of toolEntries) {
            if (entry.shortcut === shortcut)
                return entry
        }
        return null
    }

    // The focused window, found in the reading order of the centre.
    function activeGroup() {
        return keys.workspace.groups.find(group => group.id === keys.workspace.activeGroup) || null
    }

    function cycleTab(step) {
        const group = activeGroup()
        if (group === null || group.tabs.length < 2)
            return
        const index = group.tabs.findIndex(tab => tab.id === group.active)
        const next = group.tabs[(index + step + group.tabs.length) % group.tabs.length]
        keys.workspace.activateTab(group.id, next.id)
    }

    // The focused dock: the left one when it is open, else the right one. ``direction`` is +1 for
    // Right and -1 for Left; on the right dock the edge is its left side, so the sign flips there.
    function resizeFocusedDock(direction) {
        if (keys.workspace.fullscreen)
            return
        const side = dockOpen("left") ? "left" : dockOpen("right") ? "right" : ""
        if (side === "")
            return
        const sign = side === "left" ? 1 : -1
        keys.workspace.setDockWidth(side, keys.workspace.dockState(side).width + sign * direction * 24)
    }

    // Playback
    Shortcut {
        sequence: "Space"
        autoRepeat: false
        enabled: keys.window.active && keys.workspace.playingId.length > 0 && !keys.textInputFocused()
        onActivated: keys.workspace.togglePlay()
    }
    Shortcut {
        sequence: "Ctrl+Right"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.next()
    }
    Shortcut {
        sequence: "Ctrl+Left"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.previous()
    }

    // Windows: the docks, the tool windows, the centre windows and their tabs.
    Shortcut {
        sequence: "Ctrl+B"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.toggleDock("left")
    }
    Shortcut {
        sequence: "Ctrl+Alt+B"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.toggleDock("right")
    }
    // Each shortcut sits in an Item of the Repeater: a Shortcut under a non-visual parent never
    // gets the window's context.
    Repeater {
        model: 5
        delegate: Item {
            required property int index
            readonly property var toolWindow: keys.toolWindowFor("Alt+" + (index + 1))

            Shortcut {
                sequence: "Alt+" + (index + 1)
                enabled: parent.toolWindow !== null && !keys.textInputFocused() && !keys.workspace.fullscreen
                onActivated: keys.workspace.toggleToolWindow(parent.toolWindow.id)
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+I"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.toggleToolWindow("info")
    }
    Shortcut {
        sequence: "Alt+Q"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.toggleToolWindow("queue")
    }
    Shortcut {
        sequence: "Alt+H"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.toggleToolWindow("history")
    }
    Shortcut {
        sequence: "Ctrl+Shift+E"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.openToolWindow("explorer", false)
    }
    Shortcut {
        sequence: "Ctrl+,"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.openSettings()
    }
    // Split the focused window with its active tab: right (Ctrl+\) or down (Ctrl+Shift+\), plan 131.7.
    Shortcut {
        sequence: "Ctrl+\\"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.splitWithTab(keys.workspace.activeGroup, "right",
            keys.workspace.activeGroup, keys.workspace.activeTabId)
    }
    Shortcut {
        sequence: "Ctrl+Shift+\\"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.splitWithTab(keys.workspace.activeGroup, "bottom",
            keys.workspace.activeGroup, keys.workspace.activeTabId)
    }
    Repeater {
        model: 9
        delegate: Item {
            required property int index

            Shortcut {
                sequence: "Ctrl+" + (index + 1)
                enabled: keys.workspace.groups.length > index && !keys.textInputFocused()
                onActivated: keys.workspace.focusGroup(keys.workspace.groups[index].id)
            }
        }
    }
    Shortcut {
        sequence: "Ctrl+Tab"
        enabled: !keys.textInputFocused() && keys.activeGroup() !== null && keys.activeGroup().tabs.length > 1
        onActivated: keys.cycleTab(1)
    }
    Shortcut {
        sequence: "Ctrl+Shift+Tab"
        enabled: !keys.textInputFocused() && keys.activeGroup() !== null && keys.activeGroup().tabs.length > 1
        onActivated: keys.cycleTab(-1)
    }
    Shortcut {
        sequence: "Ctrl+Alt+Left"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.moveTabToNeighbour("left")
    }
    Shortcut {
        sequence: "Ctrl+Alt+Right"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.moveTabToNeighbour("right")
    }
    Shortcut {
        sequence: "Ctrl+Alt+Up"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.moveTabToNeighbour("top")
    }
    Shortcut {
        sequence: "Ctrl+Alt+Down"
        enabled: keys.hasActiveTab() && !keys.textInputFocused()
        onActivated: keys.workspace.moveTabToNeighbour("bottom")
    }
    Shortcut {
        sequence: "Ctrl+W"
        enabled: keys.workspace.groups.length > 0 && keys.hasActiveTab()
        onActivated: keys.workspace.closeTab(keys.workspace.activeGroup, keys.workspace.activeTabId)
    }
    Shortcut {
        sequence: "Ctrl+Shift+W"
        enabled: keys.workspace.groups.length > 1 && !keys.textInputFocused()
        onActivated: keys.workspace.closeGroup(keys.workspace.activeGroup)
    }
    Shortcut {
        sequence: "Ctrl+Shift+Left"
        enabled: !keys.textInputFocused() && !keys.workspace.fullscreen
        onActivated: keys.resizeFocusedDock(-1)
    }
    Shortcut {
        sequence: "Ctrl+Shift+Right"
        enabled: !keys.textInputFocused() && !keys.workspace.fullscreen
        onActivated: keys.resizeFocusedDock(1)
    }

    // Navigation: the history of the centre, and the windows by reading order.
    Shortcut {
        sequence: "Alt+Left"
        enabled: keys.workspace.canNavigateBack === true && !keys.textInputFocused()
        onActivated: keys.workspace.navigateBack()
    }
    Shortcut {
        sequence: "Alt+Right"
        enabled: keys.workspace.canNavigateForward === true && !keys.textInputFocused()
        onActivated: keys.workspace.navigateForward()
    }

    // Editing
    Shortcut {
        sequence: "Ctrl+Z"
        enabled: !keys.textInputFocused()
        onActivated: keys.workspace.undoSave()
    }
    Shortcut {
        sequence: "Del"
        enabled: !shell.demoMode && keys.explorerShown() && keys.workspace.selectedIds.length > 0
            && !keys.textInputFocused()
        onActivated: keys.workspace.trashModel.request_recycle(keys.workspace.selectedIds)
    }

    // Fullscreen player and the floating docks: Esc leaves the top layer first.
    Shortcut {
        sequence: "F11"
        onActivated: keys.workspace.setFullscreen(!keys.workspace.fullscreen)
    }
    Shortcut {
        sequences: ["PgDown", "Down"]
        enabled: keys.workspace.fullscreen && keys.workspace.playingId.length > 0 && !keys.textInputFocused()
            && !keys.queueListFocused()
        onActivated: keys.workspace.setFullscreenPage(1)
    }
    Shortcut {
        sequences: ["PgUp", "Up"]
        enabled: keys.workspace.fullscreen && keys.workspace.playingId.length > 0 && !keys.textInputFocused()
            && !keys.queueListFocused()
        onActivated: keys.workspace.setFullscreenPage(0)
    }
    Shortcut {
        sequence: "Esc"
        enabled: keys.workspace.fullscreen
        onActivated: keys.workspace.setFullscreen(false)
    }
    Shortcut {
        sequence: "Esc"
        enabled: !keys.workspace.fullscreen && keys.overlayDocks && (keys.dockOpen("left") || keys.dockOpen("right"))
        onActivated: {
            if (keys.dockOpen("left"))
                keys.workspace.toggleDock("left")
            if (keys.dockOpen("right"))
                keys.workspace.toggleDock("right")
        }
    }
}
