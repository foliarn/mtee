import QtQuick
import Mtee

// The SidebarSections of the plugins that chose an activity, one under the other. In a core
// activity (Playlists, Explorer) it is the footer of the list and every section has its header;
// in the pane of a plugin activity a single section has no header of its own.
Column {
    id: sections

    required property var workspace
    // "playlists", "explorer" or "<plugin_id>.<activity_id>".
    required property string activity
    property bool coreActivity: true
    // "compact" (tree rows, Explorer) or "regular" (the Playlists list, plan 132.4).
    property string rowSize: "compact"
    readonly property var ui: workspace.pluginUi
    readonly property var declared: ui ? ui.sections(activity) : []
    // The reference of the active editor tab, to mark the current row.
    readonly property string activeRef: {
        const groups = workspace.groups
        if (groups.length === 0)
            return ""
        const id = workspace.activeTabId
        return id.substring(id.indexOf(":") + 1)
    }

    objectName: "pluginSections"
    visible: declared.length > 0

    Item { width: 1; height: sections.coreActivity && sections.declared.length > 0 ? 8 : 0 }

    Repeater {
        model: sections.declared
        delegate: PluginSection {
            required property var modelData
            workspace: sections.workspace
            width: sections.width
            sectionKey: modelData.key
            title: modelData.title
            actions: modelData.actions
            showHeader: sections.coreActivity || sections.declared.length > 1
            rowSize: sections.rowSize
            readonly property var rowsModel: sections.ui.sectionModel(modelData.key)
            items: rowsModel ? rowsModel.items : []
            activeId: sections.activeRef
        }
    }

    Item { width: 1; height: sections.coreActivity && sections.declared.length > 0 ? 12 : 0 }
}
