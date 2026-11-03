import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// The Plugins activity (plan 123.6, placement B): a search field, the Installed plugins and the
// Marketplace list. A row opens the plugin's detail as an editor tab. Every action goes to
// workspace.pluginsView; QML passes ids and file URLs only.
Item {
    id: pane

    required property var workspace
    readonly property var view: workspace.pluginsView
    readonly property var installedRows: view ? view.installed : []
    readonly property var marketRows: view ? view.marketplace : []
    readonly property bool searching: view ? view.search.trim().length > 0 : false
    // Text for a StyledText label: the characters that the rich-text parser reads are escaped.
    function escapeText(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }
    // The tab ref of the open plugin: a plugin id, or a Marketplace key ("id@address").
    readonly property string activeId: {
        const groups = pane.workspace.groups
        if (groups.length === 0)
            return ""
        const active = groups[pane.workspace.activeGroup].active
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

            Item {
                width: parent.width
                height: 30

                SectionLabel {
                    x: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Installed"
                }
            }

            Repeater {
                model: pane.installedRows
                delegate: Item {
                    id: installedRow
                    required property var modelData
                    readonly property bool selected: modelData.id === pane.activeId
                    readonly property color stateColor: modelData.status === "failed" ? Theme.danger
                        : modelData.status === "restart" ? Theme.warning
                        : modelData.status === "running" ? Theme.primary : Theme.textMuted
                    width: column.width
                    height: 32
                    objectName: "pluginsInstalled_" + modelData.id

                    Rectangle {
                        anchors.fill: parent
                        color: installedRow.selected ? Theme.selection
                            : hit.containsMouse ? Theme.surface : "transparent"
                    }

                    PluginLetterTile {
                        x: 16
                        anchors.verticalCenter: parent.verticalCenter
                        letter: installedRow.modelData.letter
                    }

                    Text {
                        id: installedStatus
                        anchors.right: parent.right
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        text: installedRow.modelData.statusText
                        color: installedRow.stateColor
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 44
                        anchors.right: installedStatus.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        text: installedRow.modelData.title
                        elide: Text.ElideRight
                        color: installedRow.selected ? Theme.primary : Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    MouseArea {
                        id: hit
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: if (pane.view) pane.view.openDetail(installedRow.modelData.id)
                    }
                }
            }

            Text {
                objectName: "pluginsInstalledEmpty"
                x: 16
                width: column.width - 32
                visible: pane.installedRows.length === 0
                wrapMode: Text.WordWrap
                text: pane.searching ? "No installed plugin matches the search." : "No plugin is installed."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Item {
                width: parent.width
                height: 30

                SectionLabel {
                    x: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Marketplace"
                }
            }

            Text {
                objectName: "marketplaceLoading"
                x: 16
                width: column.width - 32
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
                visible: pane.view !== null && pane.view.marketplaceState === "ready"
                    && pane.marketRows.length === 0
                wrapMode: Text.WordWrap
                text: pane.searching ? "No Marketplace plugin matches the search." : "No plugins are listed yet."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Repeater {
                model: pane.marketRows
                delegate: Item {
                    id: marketRow
                    required property var modelData
                    readonly property bool selected: modelData.key === pane.activeId
                    width: column.width
                    height: 32
                    objectName: "pluginsMarket_" + modelData.key

                    Rectangle {
                        anchors.fill: parent
                        color: marketRow.selected ? Theme.selection
                            : marketHit.containsMouse ? Theme.surface : "transparent"
                    }

                    PluginLetterTile {
                        x: 16
                        anchors.verticalCenter: parent.verticalCenter
                        letter: marketRow.modelData.letter
                    }

                    Text {
                        id: marketState
                        anchors.right: parent.right
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        text: marketRow.modelData.state === "update" ? "Update to " + marketRow.modelData.version
                            : marketRow.modelData.state === "installed" ? "Installed" : "Install"
                        color: marketRow.modelData.state === "update" ? Theme.primary : Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 44
                        anchors.right: marketState.left
                        anchors.rightMargin: 8
                        anchors.verticalCenter: parent.verticalCenter
                        // A plugin listed by two marketplaces shows which list this entry comes from.
                        textFormat: Text.StyledText
                        text: pane.escapeText(marketRow.modelData.title)
                            + (marketRow.modelData.duplicate === true
                                ? " <font color=\"" + Theme.textMuted + "\">· " + pane.escapeText(marketRow.modelData.sourceTitle) + "</font>"
                                : "")
                        elide: Text.ElideRight
                        color: marketRow.selected ? Theme.primary : Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    MouseArea {
                        id: marketHit
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: if (pane.view) pane.view.openDetail(marketRow.modelData.key)
                    }
                }
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
