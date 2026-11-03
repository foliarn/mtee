import QtQuick
import QtQuick.Controls.Basic

// A menu built from data (plan 130). ``groups`` is
// [{id, items: [{id, label, hint, icon, enabled, visible, danger, objectName, submenu: [...]}]}].
// A hidden item and an empty group draw nothing; one separator sits between two non-empty
// groups. ``triggered`` carries the id of the chosen item, also from a sub menu. A caller adds
// its own groups (a plugin's) by id: it puts them in ``groups`` where it wants them.
AppMenu {
    id: menu

    property var groups: []
    signal triggered(string actionId)

    property var built: []

    Component {
        id: itemComponent
        AppMenuItem {}
    }
    Component {
        id: separatorComponent
        AppMenuSeparator {}
    }

    function clearBuilt() {
        for (const entry of built) {
            if (entry.menu) {
                removeMenu(entry.object)
            } else {
                removeItem(entry.object)
            }
            entry.object.destroy()
        }
        built = []
    }

    function visibleItems(group) {
        return (group.items || []).filter(entry => entry.visible !== false)
    }

    function rebuild() {
        clearBuilt()
        let first = true
        for (const group of groups) {
            const entries = visibleItems(group)
            if (entries.length === 0)
                continue
            if (!first)
                addBuilt(separatorComponent.createObject(null, { "objectName": "separator_" + group.id }), false)
            first = false
            for (const entry of entries)
                addEntry(entry)
        }
    }

    function addEntry(entry) {
        if (entry.submenu && entry.submenu.length > 0) {
            const sub = Qt.createComponent("ActionMenu.qml").createObject(menu, {
                "title": entry.label,
                "objectName": entry.objectName || ("submenu_" + entry.id),
                "groups": [{ "id": entry.id, "items": entry.submenu }]
            })
            sub.triggered.connect(actionId => menu.triggered(actionId))
            built.push({ "object": sub, "menu": true })
            addMenu(sub)
            return
        }
        const item = itemComponent.createObject(null, {
            "text": entry.label,
            "hint": entry.hint || "",
            "iconName": entry.icon || "",
            "danger": entry.danger === true,
            "enabled": entry.enabled !== false,
            "objectName": entry.objectName || ("action_" + entry.id)
        })
        item.triggered.connect(() => menu.triggered(entry.id))
        addBuilt(item, false)
    }

    function addBuilt(object, isMenu) {
        built.push({ "object": object, "menu": isMenu })
        addItem(object)
    }

    onGroupsChanged: rebuild()
    Component.onCompleted: rebuild()
    Component.onDestruction: clearBuilt()
}
