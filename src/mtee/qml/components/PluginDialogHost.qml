import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The modal popup of a plugin's PluginDialog, drawn like the dialogs of the playlists (surface,
// separator border, radius 8, 20 px padding). The plugin's QML file is its content: it sets its
// own title, fields and buttons, and gives its implicitHeight. It receives ``workspace``,
// ``backend``, ``ref`` (the text the plugin gave to open_dialog) and ``dialog`` (this item,
// whose ``close()`` closes the popup).
Item {
    id: host

    required property var workspace
    readonly property var ui: workspace.pluginUi
    property string key: ""
    property string ref: ""
    readonly property bool opened: popup.opened
    readonly property var content: loader.item

    objectName: "pluginDialogHost"

    function close() {
        popup.close()
    }

    Connections {
        target: host.ui
        function onDialogRequested(key, ref) {
            host.key = key
            host.ref = ref
            loader.source = host.ui.dialogQml(key)
            popup.open()
        }
    }

    Popup {
        id: popup
        objectName: "pluginDialog"
        parent: Overlay.overlay
        width: Math.min(480, parent.width - 32)
        height: loader.height + 40
        x: (parent.width - width) / 2
        y: Math.max(16, (parent.height - height) / 2)
        modal: true
        focus: true
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        onClosed: loader.source = ""

        contentItem: Loader {
            id: loader
            width: popup.width - 40
            height: item ? item.implicitHeight : 0
            onLoaded: {
                item.workspace = host.workspace
                item.backend = host.ui.dialogBackend(host.key)
                item.dialog = host
                item.ref = Qt.binding(() => host.ref)
            }
        }
    }
}
