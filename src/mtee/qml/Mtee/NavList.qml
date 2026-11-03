import QtQuick

// A list of NavItem rows with the selection rules shared by the sidebars (plan 130): a click
// selects one row, Ctrl+click toggles it, Shift+click extends from the anchor, all by row id and
// across depths. The model is an array of objects or a ListModel; a row is
// {id, title, subtitle, leading, tag, tagTone, depth, expandable, expanded, dropTarget, renaming}.
// Up/Down move the selection, Enter emits ``activated``. Pressing and dragging a row emits
// ``rowDragStarted`` with the ids to drag (the selection when the row is part of it).
ListView {
    id: list

    // "compact" or "regular", see NavItem.
    property string size: "regular"
    property var selectedIds: []
    property string anchorId: ""
    readonly property int rowHeight: size === "compact" ? 28 : 52
    signal selectionUpdated()
    signal activated(string rowId)
    signal rowDoubleClicked(string rowId)
    signal rowContextRequested(string rowId, real x, real y)
    signal rowChevronClicked(string rowId)
    signal rowRenamed(string rowId, string text)
    signal rowDragStarted(var ids)

    function rowAt(index) {
        if (model && typeof model.length === "number")
            return model[index]
        if (model && typeof model.get === "function")
            return model.get(index)
        return null
    }

    function rowCount() {
        if (model && typeof model.length === "number")
            return model.length
        return model && model.count !== undefined ? model.count : 0
    }

    function idAt(index) {
        const row = rowAt(index)
        return row ? String(row.id) : ""
    }

    function indexOfId(rowId) {
        for (let i = 0; i < rowCount(); ++i) {
            if (idAt(i) === rowId)
                return i
        }
        return -1
    }

    function isSelected(rowId) {
        return selectedIds.indexOf(rowId) >= 0
    }

    function setSelection(ids, anchor) {
        selectedIds = ids
        anchorId = anchor
        selectionUpdated()
    }

    // Applies the click rules to the row at ``index``; ``modifiers`` are the Qt keyboard modifiers.
    function select(index, modifiers) {
        const rowId = idAt(index)
        if (rowId.length === 0)
            return
        if (modifiers & Qt.ShiftModifier) {
            const from = indexOfId(anchorId)
            const start = Math.min(from < 0 ? index : from, index)
            const end = Math.max(from < 0 ? index : from, index)
            const range = []
            for (let i = start; i <= end; ++i)
                range.push(idAt(i))
            setSelection(range, from < 0 ? rowId : anchorId)
        } else if (modifiers & Qt.ControlModifier) {
            const next = selectedIds.filter(value => value !== rowId)
            if (next.length === selectedIds.length)
                next.push(rowId)
            setSelection(next, rowId)
        } else {
            setSelection([rowId], rowId)
        }
        currentIndex = index
    }

    clip: true
    activeFocusOnTab: true
    boundsBehavior: Flickable.StopAtBounds
    keyNavigationEnabled: false

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Down || event.key === Qt.Key_Up) {
            const count = rowCount()
            if (count === 0)
                return
            const start = currentIndex < 0 ? (event.key === Qt.Key_Down ? -1 : count) : currentIndex
            const next = Math.max(0, Math.min(count - 1, start + (event.key === Qt.Key_Down ? 1 : -1)))
            select(next, event.modifiers & Qt.ShiftModifier)
            positionViewAtIndex(next, ListView.Contain)
            event.accepted = true
        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && currentIndex >= 0) {
            activated(idAt(currentIndex))
            event.accepted = true
        }
    }

    WheelScrollHandler { flickable: list }

    delegate: NavItem {
        id: row

        required property int index
        readonly property var rowData: list.rowAt(index) || ({})

        width: list.width
        size: list.size
        height: list.rowHeight
        leading: rowData.leading || ""
        title: rowData.title || ""
        subtitle: rowData.subtitle || ""
        tag: rowData.tag || ""
        tagTone: rowData.tagTone || "neutral"
        depth: rowData.depth || 0
        expandable: rowData.expandable === true
        expanded: rowData.expanded === true
        dropTarget: rowData.dropTarget === true
        renaming: rowData.renaming === true
        selected: list.isSelected(String(rowData.id))
        objectName: "navRow_" + rowData.id

        onClicked: (modifiers) => {
            list.forceActiveFocus()
            list.select(row.index, modifiers)
        }
        onDoubleClicked: list.rowDoubleClicked(String(row.rowData.id))
        onContextRequested: (x, y) => {
            if (!row.selected)
                list.select(row.index, 0)
            list.rowContextRequested(String(row.rowData.id), x, y)
        }
        onChevronClicked: list.rowChevronClicked(String(row.rowData.id))
        onRenamed: (text) => list.rowRenamed(String(row.rowData.id), text)
        onDragStarted: {
            if (!row.selected)
                list.select(row.index, 0)
            list.rowDragStarted(list.selectedIds)
        }
    }
}
