import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The detail tab of a plugin (tab kind "plugin", ref = plugin id or Marketplace key "id@address"), built like the Settings tab:
// the heading, then Status (installed), the install or update action, Details, About and Remove
// (installed). The row comes from workspace.pluginsView.detail(id) and is read again at each change
// of the view. Nothing here touches a file: the switch, the actions and the removal are slots.
Rectangle {
    id: detail

    required property var workspace
    property var tab
    property int groupIndex: 0
    property int bottomInset: 0
    readonly property var pluginsView: workspace.pluginsView
    readonly property string pluginId: tab ? String(tab.ref) : ""
    // The row of the plugin: an installed plugin, or a Marketplace entry that is not installed.
    property var row: ({})
    // The Marketplace entry of the plugin (the row itself when it is not installed).
    property var offer: ({})
    readonly property bool installed: row.status !== undefined
    readonly property bool missing: pluginId.length > 0 && Object.keys(row).length === 0
    readonly property bool updateAvailable: installed && !!row.updateVersion
    readonly property string actionText: updateAvailable ? "Update to " + row.updateVersion
        : offer.state === "install" ? "Install"
        : offer.state === "update" ? "Update to " + offer.version
        : offer.state === "installed" ? "Installed" : ""
    readonly property bool actionEnabled: updateAvailable || offer.state === "install" || offer.state === "update"

    objectName: "pluginDetail"
    color: Theme.editor

    function refresh() {
        const view = detail.pluginsView
        const found = view && detail.pluginId.length > 0 ? view.detail(detail.pluginId) : ({})
        let entry = found
        if (found.status !== undefined && view) {
            // An installed plugin's offer is the Marketplace entry named by its offerKey.
            const listed = view.marketplace.find(item => item.key === found.offerKey)
            entry = listed === undefined ? ({}) : listed
        }
        detail.row = found
        detail.offer = entry
    }

    function runAction() {
        const view = detail.pluginsView
        if (!view)
            return
        if (detail.updateAvailable || detail.offer.state === "update") {
            const key = detail.installed && detail.row.offerKey ? detail.row.offerKey : detail.pluginId
            view.update(key)
        } else if (detail.offer.state === "install") {
            view.install(detail.offer.key || detail.pluginId)
        }
    }

    Component.onCompleted: refresh()
    onPluginIdChanged: refresh()

    Connections {
        target: detail.pluginsView
        ignoreUnknownSignals: true
        function onChanged() { detail.refresh() }
    }

    Flickable {
        anchors.fill: parent
        contentHeight: content.implicitHeight + 48 + detail.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: content
            x: 24
            width: Math.min(720, detail.width - 48)
            spacing: 8

            Item { width: 1; height: 30 }

            SectionLabel { text: "Plugin" }

            Text {
                objectName: "pluginDetailTitle"
                width: parent.width
                wrapMode: Text.WordWrap
                text: detail.row.title || (detail.tab ? detail.tab.title : "")
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeHeading
                font.weight: Font.Bold
            }

            Text {
                objectName: "pluginDetailByline"
                width: parent.width
                topPadding: 2
                visible: !detail.missing
                text: (detail.row.author ? detail.row.author + " · " : "") + "version " + (detail.row.version || "")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            // The Marketplace list a plugin that is not installed comes from.
            Text {
                objectName: "pluginDetailFrom"
                width: parent.width
                topPadding: 2
                visible: !detail.missing && !detail.installed && (detail.row.sourceTitle || "").length > 0
                text: "From " + (detail.row.sourceTitle || "")
                elide: Text.ElideRight
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                objectName: "pluginDetailGone"
                width: parent.width
                topPadding: 16
                visible: detail.missing
                wrapMode: Text.WordWrap
                text: "This plugin was uninstalled. Restart MTEE to finish."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            // Status: only for an installed plugin; the switch applies after a restart.
            Column {
                visible: detail.installed
                width: content.width
                spacing: 8

                Group { title: "Status" }

                ToggleRow {
                    objectName: "pluginDetailSwitch"
                    label: "Switched on"
                    description: "Changes apply after MTEE restarts."
                    checked: detail.row.enabled === true
                    onToggled: (on) => { if (detail.pluginsView) detail.pluginsView.setEnabled(detail.row.id, on) }
                }

                InfoRow {
                    objectName: "pluginDetailStatus"
                    label: "Status"
                    value: detail.row.statusText || ""
                }

                Text {
                    objectName: "pluginDetailError"
                    visible: detail.row.status === "failed" && (detail.row.error || "").length > 0
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: detail.row.error || ""
                    color: Theme.danger
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }

            // The one action of the page: an update, an install, or a disabled "Installed".
            Column {
                visible: !detail.missing && detail.actionText.length > 0
                width: content.width
                spacing: 8

                Group { title: detail.updateAvailable ? "Update" : "Install" }

                ActionRow {
                    objectName: "pluginDetailAction"
                    label: "Version"
                    description: detail.installed
                        ? "Installed version " + detail.row.version
                        : "Version " + (detail.offer.version || "") + " is in the plugin list"
                    actionText: detail.actionText
                    actionKind: detail.actionEnabled ? "primary" : "ghost"
                    enabledAction: detail.actionEnabled
                    onAction: detail.runAction()
                }
            }

            Column {
                visible: !detail.missing
                width: content.width
                spacing: 8

                Group { title: "Details" }

                InfoRow { objectName: "pluginDetailLicence"; visible: !!detail.row.licence; label: "Licence"; value: detail.row.licence || "" }
                InfoRow {
                    objectName: "pluginDetailSource"
                    visible: !!detail.row.installedFrom
                    label: "Installed from"
                    value: detail.row.installedFrom === "marketplace" ? "MTEE plugin list" : "Plugin file"
                }
                InfoRow {
                    objectName: "pluginDetailLibraries"
                    visible: detail.installed
                    label: "Bundled libraries"
                    value: detail.row.librariesCount ? String(detail.row.librariesCount) : "None"
                }
                InfoRow {
                    objectName: "pluginDetailNetwork"
                    label: "Uses the network"
                    value: detail.row.usesNetwork ? "Yes" : "No"
                }
                InfoRow { objectName: "pluginDetailHomepage"; visible: !!detail.row.homepage; label: "Homepage"; value: detail.row.homepage || "" }
            }

            Column {
                visible: !detail.missing
                width: content.width
                spacing: 8

                Group { title: "About" }

                Text {
                    objectName: "pluginDetailDescription"
                    width: parent.width
                    topPadding: 4
                    visible: text.length > 0
                    text: detail.row.description || ""
                    wrapMode: Text.WordWrap
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    objectName: "pluginDetailReadme"
                    width: parent.width
                    topPadding: 8
                    visible: (detail.row.readme || "").length > 0
                    text: detail.row.readme || ""
                    wrapMode: Text.WordWrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            // Uninstall has no confirmation: the folder goes to the Recycle Bin, the data stays.
            Column {
                visible: detail.installed
                width: content.width
                spacing: 8

                Group { title: "Remove" }

                ActionRow {
                    objectName: "pluginDetailUninstall"
                    label: "Uninstall"
                    description: "The plugin goes to the Recycle Bin. Its data stays."
                    actionText: "Uninstall"
                    danger: true
                    onAction: { if (detail.pluginsView) detail.pluginsView.uninstall(detail.row.id) }
                }
            }

            Item { width: 1; height: 24 }
        }
    }
}
