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
    // The width the plugin asked for (PluginDialog.width, 320 to 640 px, 480 by default).
    property int dialogWidth: 480
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
            host.dialogWidth = host.ui.dialogWidth(key)
            loader.source = host.ui.dialogQml(key)
            popup.open()
        }
    }

    Popup {
        id: popup
        objectName: "pluginDialog"
        parent: Overlay.overlay
        width: Math.min(host.dialogWidth, parent.width - 32)
        height: (loader.item ? loader.item.implicitHeight : 0) + 40
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
            onLoaded: {
                item.workspace = host.workspace
                item.backend = host.ui.dialogBackend(host.key)
                item.dialog = host
                item.ref = Qt.binding(() => host.ref)
            }
        }
    }
}
