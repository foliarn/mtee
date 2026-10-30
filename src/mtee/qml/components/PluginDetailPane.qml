import QtQuick

// Placeholder of the detail tab of a plugin (tab kind "plugin", ref = plugin id), plan 123.6.
// The QML of the Plugins view replaces it. The tab's data is the id and the title of the tab;
// the row of the plugin comes from workspace.pluginsView.detail(id).
Item {
    required property var workspace
    property var tab
    property int groupIndex: 0
    property int bottomInset: 0
    readonly property var pluginsView: workspace.pluginsView
}
