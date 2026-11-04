import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// The Plugins activity (plan 123.6, placement B): a search field and one list of the installed and
// the Marketplace plugins (plan 132.6). A row opens the plugin's detail as an editor tab. Every
// action goes to workspace.pluginsView; QML passes ids and file URLs only.
Item {
    id: pane

    required property var workspace
    readonly property var view: workspace.pluginsView
    // The one list of the view (plan 132.6): each plugin once, in its order.
    readonly property var pluginRows: view ? view.plugins : []
    readonly property var marketRows: view ? view.marketplace : []
    readonly property bool searching: view ? view.search.trim().length > 0 : false
    // The tab ref of the open plugin: a plugin id, or a Marketplace key ("id@address").
    readonly property string activeId: {
        const groups = pane.workspace.groups
        if (groups.length === 0)
            return ""
        const active = pane.workspace.activeTabId
        return active.indexOf("plugin:") === 0 ? active.slice("plugin:".length) : ""
    }

    objectName: "pluginsViewPane"

    // The list is read once when the Marketplace is first shown; a later visit reuses it.
    Component.onCompleted: if (pane.view) pane.view.marketplaceRequested()

    PaneHeader {
        id: header
        width: parent.width
        title: "Plugins"

        IconButton {
            objectName: "pluginsInstallFromFile"
            icon: "plus"; iconSize: 16; width: 26; height: 26
            tip: "Install from file…"
            enabledAction: pane.view !== null
            onClicked: fileDialog.open()
        }

        IconButton {
            objectName: "pluginsOpenFolder"
            icon: "folder"; iconSize: 16; width: 26; height: 26
            tip: "Open plugins folder"
            enabledAction: pane.view !== null
            onClicked: pane.view.openPluginsFolder()
        }
    }

    FileDialog {
        id: fileDialog
        objectName: "pluginsFileDialog"
        title: "Install a plugin"
        nameFilters: ["MTEE plugin (*.mteeplugin)"]
        onAccepted: if (pane.view) pane.view.chooseFile(String(selectedFile))
    }

    Rectangle {
        id: searchBox
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 4
        height: 30
        color: searchInput.activeFocus ? Theme.editor : Theme.chrome
        border.width: 1
        border.color: searchInput.activeFocus ? Theme.focus : Theme.separator

        Icon {
            id: searchIcon
            x: 8
            anchors.verticalCenter: parent.verticalCenter
            name: "search"
            size: 14
            color: Theme.textMuted
        }

        TextInput {
            id: searchInput
            objectName: "pluginsSearch"
            anchors.left: searchIcon.right
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.textPrimary
            selectionColor: Theme.primary
            selectedTextColor: Theme.textOnColor
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            selectByMouse: true
            clip: true
            onTextEdited: if (pane.view) pane.view.search = text
            Keys.onEscapePressed: { text = ""; if (pane.view) pane.view.search = ""; focus = false }
            Component.onCompleted: text = pane.view ? pane.view.search : ""

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: searchInput.text.length === 0
                text: "Search plugins"
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    Flickable {
        WheelScrollHandler { flickable: list }
        id: list
        anchors.top: searchBox.bottom
        anchors.topMargin: 6
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: foot.top
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: column
            width: list.width
            topPadding: 2

            // One list (plan 132.6): installed and Marketplace plugins, each once. A tag only on an
            // installed plugin. The rows are NavItem; the letter tile is its own leading.
            Repeater {
                model: pane.pluginRows
                delegate: NavItem {
                    id: pluginRow
                    required property var modelData
                    width: column.width
                    objectName: (modelData.installed ? "pluginsInstalled_" : "pluginsMarket_") + modelData.key
                    leading: modelData.letter
                    title: modelData.title
                    tag: modelData.tag
                    tagTone: modelData.tagTone
                    warning: modelData.warning
                    selected: modelData.key === pane.activeId
                    onClicked: if (pane.view) pane.view.openDetail(modelData.key)
                }
            }

            Text {
                objectName: "pluginsEmpty"
                x: 16
                width: column.width - 32
                visible: pane.pluginRows.length === 0
                wrapMode: Text.WordWrap
                text: pane.searching ? "No plugin matches the search." : "No plugin is installed or listed yet."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Text {
                objectName: "marketplaceLoading"
                x: 16
                width: column.width - 32
                topPadding: 12
                visible: pane.view !== null && (pane.view.marketplaceState === "loading"
                    || pane.view.marketplaceState === "idle")
                wrapMode: Text.WordWrap
                text: "Reading the plugin list…"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Column {
                objectName: "marketplaceFailed"
                x: 16
                width: column.width - 32
                topPadding: 12
                visible: pane.view !== null && pane.view.marketplaceState === "failed"
                spacing: 8

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: pane.view ? pane.view.marketplaceError : ""
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                TextButton {
                    objectName: "marketplaceCheckAgain"
                    implicitHeight: 26
                    kind: "ghost"
                    text: "Check again"
                    onClicked: if (pane.view) pane.view.checkMarketplace()
                }
            }

            Text {
                objectName: "marketplaceEmpty"
                x: 16
                width: column.width - 32
                topPadding: 12
                visible: pane.view !== null && pane.view.marketplaceState === "ready"
                    && pane.marketRows.length === 0
                wrapMode: Text.WordWrap
                text: pane.searching ? "No Marketplace plugin matches the search." : "No plugins are listed yet."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    // The foot: when the plugin list was last read, and what waits for a restart.
    Rectangle {
        id: foot
        anchors.bottom: parent.bottom
        width: parent.width
        height: footColumn.implicitHeight + 24
        color: "transparent"

        Rectangle {
            width: parent.width
            height: 1
            color: Theme.separator
            opacity: 0.6
        }

        Column {
            id: footColumn
            x: 16
            y: 12
            width: parent.width - 32
            spacing: 6

            Row {
                spacing: 8

                Text {
                    objectName: "pluginsLastChecked"
                    anchors.verticalCenter: parent.verticalCenter
                    text: pane.view ? pane.view.lastCheckedText : ""
                    visible: text.length > 0
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Text {
                    id: checkAgain
                    objectName: "pluginsCheckAgain"
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Check again"
                    color: checkMouse.containsMouse ? Theme.primary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall

                    MouseArea {
                        id: checkMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: if (pane.view) pane.view.checkMarketplace()
                    }
                }
            }

            Text {
                objectName: "pluginsRestartText"
                width: parent.width
                visible: pane.view !== null && pane.view.restartNeeded
                text: pane.view ? pane.view.restartText : ""
                elide: Text.ElideRight
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            TextButton {
                objectName: "pluginsRestartNow"
                visible: pane.view !== null && pane.view.restartNeeded
                implicitHeight: 26
                kind: "neutral"
                text: "Restart now"
                onClicked: if (pane.view) pane.view.restartNow()
            }
        }
    }
}
