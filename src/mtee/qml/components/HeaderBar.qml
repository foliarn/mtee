import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import Mtee

// The header of the frame (plan 131.5): logo, the hamburger menu, Back and Forward, a drag caption,
// then on the right the plugin status icons, the empty progress and bell slots (plan 134), the
// Profile button and the window buttons. ``windowFrame`` gets the caption as the free space between
// the left group and the right group, so every button on either side stays clickable.
Rectangle {
    id: bar

    required property var window
    required property var workspace
    readonly property bool maximized: window.visibility === Window.Maximized
    readonly property string activeTabKind: (workspace.activeTabId || "").split(":")[0]
    readonly property int captionLeft: leftGroup.x + leftGroup.width + 8
    readonly property int rightWidth: width - rightGroup.x
    // The narrow-window rules (plan 131.9): Back and Forward go first, then the status icons.
    readonly property bool navigationShown: width >= Theme.singleWindowWidth
    readonly property bool statusShown: width >= Theme.headerStatusWidth

    // Bumped on every layout change, so the View marks are read again (the dock state is a call).
    property int layoutRevision: 0
    Connections {
        target: bar.workspace
        function onLayoutChanged() { bar.layoutRevision++ }
    }
    function dockOpen(side) {
        layoutRevision
        return bar.workspace.dockState(side).open === true
    }
    function windowShown(windowId) {
        layoutRevision
        const side = bar.workspace.toolWindows.sideOf(windowId)
        if (side.length === 0)
            return false
        const dock = bar.workspace.dockState(side)
        return dock.open === true && dock.windows.indexOf(windowId) >= 0
    }
    signal selectAllRequested()

    height: Theme.frameSize
    color: Theme.chrome

    function declareRegions() {
        windowFrame.setTitleBar(height, captionLeft, Theme.windowButtonWidth, rightWidth)
    }

    onWidthChanged: declareRegions()
    onHeightChanged: declareRegions()
    onCaptionLeftChanged: declareRegions()
    onRightWidthChanged: declareRegions()
    Component.onCompleted: declareRegions()

    MouseArea {
        id: caption
        anchors.fill: parent
        enabled: !windowFrame.native
        acceptedButtons: Qt.LeftButton
        onPressed: bar.window.startSystemMove()
        onDoubleClicked: windowFrame.toggleMaximized()
    }

    Row {
        id: leftGroup
        anchors.left: parent.left
        height: parent.height

        // The application logo, from resources/brand next to the QML tree.
        Image {
            id: logo
            objectName: "headerLogo"
            width: Theme.frameSize
            height: parent.height
            fillMode: Image.PreserveAspectFit
            sourceSize: Qt.size(64, 64)
            smooth: true
            source: Qt.resolvedUrl("../../resources/brand/mtee-64.png")
        }

        HeaderButton {
            id: hamburger
            objectName: "hamburgerButton"
            icon: "menu"
            tip: "Menu"
            onClicked: appMenu.popup(hamburger, 0, hamburger.height)
        }

        // Below the single-window width Back and Forward leave the header; the menu keeps them.
        HeaderButton {
            objectName: "navigateBackButton"
            visible: bar.navigationShown
            icon: "arrow-left"
            tip: "Back (Alt+Left)"
            enabledAction: bar.workspace.canNavigateBack === true
            onClicked: bar.workspace.navigateBack()
        }

        HeaderButton {
            objectName: "navigateForwardButton"
            visible: bar.navigationShown
            icon: "arrow-right"
            tip: "Forward (Alt+Right)"
            enabledAction: bar.workspace.canNavigateForward === true
            onClicked: bar.workspace.navigateForward()
        }
    }

    Row {
        id: rightGroup
        objectName: "headerRight"
        anchors.right: parent.right
        height: parent.height

        // Plugin status items: an icon each, the text in its tooltip, the same click as before.
        // Below the status width the plugin items leave the header; the hamburger menu lists them.
        Row {
            id: statusIcons
            objectName: "statusIcons"
            visible: bar.statusShown
            height: parent.height

            Repeater {
                model: bar.workspace.statusBar ? bar.workspace.statusBar : null

                delegate: Rectangle {
                    id: entry

                    readonly property color toneColor: model.tone === "warning" ? Theme.warning
                        : model.tone === "secondary" ? Theme.secondary : Theme.textSecondary

                    objectName: "statusItem"
                    width: 32
                    height: statusIcons.height
                    radius: Theme.radiusControl
                    color: entryMouse.containsMouse && model.clickable ? Theme.surface : "transparent"

                    Icon {
                        id: statusIcon
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.verticalCenterOffset: -3
                        name: model.icon
                        size: 16
                        color: entry.toneColor
                    }

                    // The progress of the item: a 2 px line under the icon.
                    Rectangle {
                        visible: model.progress >= 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: statusIcon.bottom
                        anchors.topMargin: 2
                        width: 16
                        height: 2
                        color: Theme.selection

                        Rectangle {
                            width: parent.width * Math.max(0, Math.min(1, model.progress))
                            height: parent.height
                            color: Theme.primary
                        }
                    }

                    MouseArea {
                        id: entryMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: model.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: if (model.clickable) bar.workspace.statusBar.activate(index)
                    }

                    HoverTip {
                        objectName: "statusItemText"
                        visible: entryMouse.containsMouse && text.length > 0
                        text: model.tooltip.length > 0 ? model.text + "\n" + model.tooltip : model.text
                    }
                }
            }
        }

        // Reserved for the task progress strip and the notifications bell (plan 134).
        Item {
            objectName: "progressSlot"
            width: 0
            height: parent.height
        }

        Item {
            objectName: "bellSlot"
            width: 0
            height: parent.height
        }

        HeaderButton {
            objectName: "activity-profile"
            icon: "profile"
            tip: "Profile"
            active: bar.activeTabKind === "profile" && !bar.workspace.fullscreen
            onClicked: bar.workspace.openProfile()
        }

        Row {
            id: buttons
            height: parent.height

            WindowButton {
                icon: "win-minimize"
                onClicked: bar.window.showMinimized()
            }

            WindowButton {
                icon: bar.maximized ? "win-restore" : "win-maximize"
                nativeHovered: windowFrame.maximizeHovered
                nativePressed: windowFrame.maximizePressed
                onClicked: windowFrame.toggleMaximized()
            }

            WindowButton {
                icon: "win-close"
                closeButton: true
                onClicked: bar.window.close()
            }
        }
    }

    component WindowButton: Rectangle {
        id: windowButton

        property string icon: ""
        property bool closeButton: false
        property bool nativeHovered: false
        property bool nativePressed: false
        readonly property bool hot: buttonMouse.containsMouse || nativeHovered
        signal clicked()

        width: Theme.windowButtonWidth
        height: bar.height
        color: hot ? (closeButton ? Theme.closeHover : (buttonMouse.pressed || nativePressed ? Theme.selection : Theme.surface))
            : "transparent"

        Icon {
            anchors.centerIn: parent
            name: windowButton.icon
            size: 16
            color: windowButton.hot ? Theme.textPrimary : Theme.textSecondary
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: true
            onClicked: windowButton.clicked()
        }
    }

    // Today's menu entries, regrouped: Library, Edit, View, Help and Exit. The split editor and the
    // player island entries are gone (plan 131.5).
    AppMenu {
        id: appMenu
        objectName: "appMenu"

        // Plugin status items, listed here while the header is too narrow to show them (plan 131.9).
        Instantiator {
            active: !bar.statusShown
            model: bar.workspace.statusBar ? bar.workspace.statusBar : null

            delegate: AppMenuItem {
                objectName: "menuStatusItem"
                text: model.text
                enabled: model.clickable === true
                onTriggered: bar.workspace.statusBar.activate(index)
            }

            onObjectAdded: (index, object) => appMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => appMenu.removeItem(object)
        }

        // Back and Forward, listed here while the header hides them.
        AppMenuItem {
            objectName: "menuNavigateBack"
            visible: !bar.navigationShown
            text: "Back"
            hint: "Alt+Left"
            enabled: bar.workspace.canNavigateBack === true
            onTriggered: bar.workspace.navigateBack()
        }
        AppMenuItem {
            objectName: "menuNavigateForward"
            visible: !bar.navigationShown
            text: "Forward"
            hint: "Alt+Right"
            enabled: bar.workspace.canNavigateForward === true
            onTriggered: bar.workspace.navigateForward()
        }
        AppMenuSeparator { visible: !bar.navigationShown || !bar.statusShown }

        AppMenuItem { text: "Add folder…"; enabled: false }
        AppMenuItem { text: "New playlist"; onTriggered: bar.workspace.addToNewPlaylist([]) }
        AppMenuItem {
            visible: bar.workspace.pluginUiEnabled
            text: "Convert selection"
            enabled: bar.workspace.selectedIds.length > 0
            onTriggered: { bar.workspace.addSelectionToConvert(); bar.workspace.openConvert() }
        }
        AppMenuSeparator {}
        AppMenuItem {
            text: "Undo last edit"
            hint: "Ctrl+Z"
            enabled: bar.workspace.saveState === "saved" || bar.workspace.saveState === "error"
            onTriggered: bar.workspace.undoSave()
        }
        AppMenuItem { text: "Select all"; hint: "Ctrl+A"; onTriggered: bar.selectAllRequested() }
        AppMenuItem {
            text: "Edit info"
            hint: "Ctrl+I"
            enabled: bar.workspace.selectedIds.length > 0
            onTriggered: bar.workspace.openToolWindow("info")
        }
        AppMenuSeparator {}
        AppMenuItem {
            text: "Left dock"
            hint: "Ctrl+B"
            mark: bar.dockOpen("left")
            onTriggered: bar.workspace.toggleDock("left")
        }
        AppMenuItem {
            text: "Right dock"
            hint: "Ctrl+Alt+B"
            mark: bar.dockOpen("right")
            onTriggered: bar.workspace.toggleDock("right")
        }
        AppMenuItem {
            text: "Info"
            hint: "Ctrl+I"
            mark: bar.windowShown("info")
            onTriggered: bar.workspace.toggleToolWindow("info")
        }
        AppMenuItem {
            text: "Queue"
            hint: "Alt+Q"
            mark: bar.windowShown("queue")
            onTriggered: bar.workspace.toggleToolWindow("queue")
        }
        AppMenuItem {
            text: "History"
            hint: "Alt+H"
            mark: bar.windowShown("history")
            onTriggered: bar.workspace.toggleToolWindow("history")
        }
        AppMenuItem {
            text: "Fullscreen player"
            hint: "F11"
            mark: bar.workspace.fullscreen
            enabled: bar.workspace.playingId.length > 0
            onTriggered: bar.workspace.setFullscreen(!bar.workspace.fullscreen)
        }
        AppMenuSeparator {}
        AppMenuItem { text: "Keyboard shortcuts"; onTriggered: bar.workspace.openSettings() }
        AppMenuItem { text: "About MTEE " + shell.applicationVersion; enabled: false }
        AppMenuSeparator {}
        AppMenuItem { text: "Exit"; hint: "Alt+F4"; onTriggered: bar.window.close() }
    }
}
