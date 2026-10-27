import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import Mtee

// Frameless title bar: logo, menus, a draggable caption and the window
// buttons. On Windows the caption and the maximize button are native hit
// regions declared to ``windowFrame``; elsewhere QML moves the window itself.
Rectangle {
    id: bar

    required property var window
    required property var workspace
    readonly property bool maximized: window.visibility === Window.Maximized
    readonly property int captionLeft: menus.x + menus.width + 8
    signal selectAllRequested()

    height: Theme.titleBarHeight
    color: Theme.chrome

    function declareRegions() {
        windowFrame.setTitleBar(height, captionLeft, Theme.windowButtonWidth, buttons.width)
    }

    onWidthChanged: declareRegions()
    onCaptionLeftChanged: declareRegions()
    Component.onCompleted: declareRegions()

    MouseArea {
        id: caption
        anchors.fill: parent
        enabled: !windowFrame.native
        acceptedButtons: Qt.LeftButton
        onPressed: bar.window.startSystemMove()
        onDoubleClicked: windowFrame.toggleMaximized()
    }

    // The application logo, from resources/brand next to the QML tree.
    Image {
        id: logo
        width: Theme.activityBarWidth
        height: parent.height
        fillMode: Image.PreserveAspectFit
        sourceSize: Qt.size(64, 64)
        smooth: true
        source: Qt.resolvedUrl("../../resources/brand/mtee-64.png")
    }

    Row {
        id: menus
        anchors.left: logo.right
        height: parent.height

        Repeater {
            model: [
                { "label": "File", "menu": fileMenu },
                { "label": "Edit", "menu": editMenu },
                { "label": "View", "menu": viewMenu },
                { "label": "Help", "menu": helpMenu }
            ]

            delegate: Rectangle {
                id: menuButton
                required property var modelData
                width: menuLabel.implicitWidth + 20
                height: menus.height
                color: menuMouse.containsMouse || modelData.menu.visible ? Theme.surface : "transparent"

                Text {
                    id: menuLabel
                    anchors.centerIn: parent
                    text: menuButton.modelData.label
                    color: menuMouse.containsMouse || menuButton.modelData.menu.visible ? Theme.textPrimary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                MouseArea {
                    id: menuMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: menuButton.modelData.menu.popup(menuButton, 0, menuButton.height)
                }
            }
        }
    }

    Row {
        id: buttons
        anchors.right: parent.right
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

    AppMenu {
        id: fileMenu
        objectName: "fileMenu"
        AppMenuItem { text: "Add folder…"; hint: "Ctrl+O"; enabled: false }
        AppMenuItem { text: "New playlist"; onTriggered: bar.workspace.addToNewPlaylist([]) }
        AppMenuSeparator {}
        AppMenuItem {
            visible: bar.workspace.pluginUiEnabled
            text: "Convert selection"
            enabled: bar.workspace.selectedIds.length > 0
            onTriggered: { bar.workspace.addSelectionToConvert(); bar.workspace.openConvert() }
        }
        AppMenuSeparator {}
        AppMenuItem { text: "Settings"; hint: "Ctrl+,"; onTriggered: bar.workspace.openSettings() }
        AppMenuSeparator {}
        AppMenuItem { text: "Exit"; hint: "Alt+F4"; onTriggered: bar.window.close() }
    }

    AppMenu {
        id: editMenu
        objectName: "editMenu"
        AppMenuItem {
            text: "Undo last edit"
            hint: "Ctrl+Z"
            enabled: bar.workspace.saveState === "saved" || bar.workspace.saveState === "error"
            onTriggered: bar.workspace.undoSave()
        }
        AppMenuSeparator {}
        AppMenuItem { text: "Select all"; hint: "Ctrl+A"; onTriggered: bar.selectAllRequested() }
        AppMenuItem {
            text: "Edit info"
            hint: "Ctrl+I"
            enabled: bar.workspace.selectedIds.length > 0
            onTriggered: bar.workspace.showRightPanel("info")
        }
    }

    AppMenu {
        id: viewMenu
        objectName: "viewMenu"
        AppMenuItem { text: "Explorer"; hint: "Ctrl+Shift+E"; onTriggered: bar.workspace.setActivity("explorer") }
        AppMenuItem { text: "Playlists"; onTriggered: bar.workspace.setActivity("playlists") }
        AppMenuItem {
            visible: bar.workspace.pluginUiEnabled
            text: "Convert"
            onTriggered: bar.workspace.setActivity("convert")
        }
        AppMenuItem { text: "Tasks"; onTriggered: bar.workspace.setActivity("tasks") }
        AppMenuItem { text: "Tasks page"; onTriggered: bar.workspace.openTasks() }
        AppMenuSeparator {}
        AppMenuItem {
            text: "Sidebar"
            hint: "Ctrl+B"
            mark: bar.workspace.sidebarVisible
            onTriggered: bar.workspace.toggleSidebar()
        }
        AppMenuItem {
            text: "Info panel"
            hint: "Ctrl+I"
            mark: bar.workspace.rightPanelVisible && bar.workspace.rightPanelTab === "info"
            onTriggered: bar.workspace.toggleRightPanel("info")
        }
        AppMenuItem {
            text: "Queue"
            mark: bar.workspace.rightPanelVisible && bar.workspace.rightPanelTab === "queue"
            onTriggered: bar.workspace.toggleRightPanel("queue")
        }
        AppMenuItem {
            text: "History"
            mark: bar.workspace.rightPanelVisible && bar.workspace.rightPanelTab === "history"
            onTriggered: bar.workspace.toggleRightPanel("history")
        }
        AppMenuItem {
            text: "Split editor"
            hint: "Ctrl+\\"
            mark: bar.workspace.groups.length > 1
            onTriggered: bar.workspace.toggleSplit()
        }
        AppMenuSeparator {}
        AppMenuItem {
            text: "Player island"
            mark: bar.workspace.islandEnabled
            onTriggered: bar.workspace.setIslandEnabled(!bar.workspace.islandEnabled)
        }
        AppMenuItem {
            text: "Fullscreen player"
            hint: "F11"
            mark: bar.workspace.fullscreen
            enabled: bar.workspace.playingId.length > 0
            onTriggered: bar.workspace.setFullscreen(!bar.workspace.fullscreen)
        }
    }

    AppMenu {
        id: helpMenu
        objectName: "helpMenu"
        AppMenuItem { text: "Keyboard shortcuts"; onTriggered: bar.workspace.openSettings() }
        AppMenuItem { text: "About MTEE " + shell.applicationVersion; enabled: false }
    }
}
