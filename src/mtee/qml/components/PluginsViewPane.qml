import QtQuick

// Placeholder of the Plugins activity (plan 123.6). The QML of the Plugins view replaces it.
// Its data is workspace.pluginsView: the properties and slots of PluginsViewModel.
Item {
    required property var workspace
    readonly property var pluginsView: workspace.pluginsView
}
