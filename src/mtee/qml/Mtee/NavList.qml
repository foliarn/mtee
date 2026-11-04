import QtQuick

// A list of NavItem rows with the selection rules shared by the sidebars (plan 130): a click
// selects one row, Ctrl+click toggles it, Shift+click extends from the anchor, all by row id and
// across depths. The model is an array of objects, a ListModel, or a C++ list model whose rows
// are read through the delegate's ``modelData``. A row is
// {id, title, subtitle, leading, tag, tagTone, depth, expandable, expanded, dropTarget, renaming}.
// ``decorate(data)`` may return NavItem properties (accent, muted, trailing, trailingTone,
// expandable, dropTarget...) that override the row's own values; it is re-evaluated when the
// state it reads changes. ``selectionEnabled: false`` leaves the selection to the owner, which
// then sets ``selectedIds``. Up/Down move the selection, Enter emits ``activated``. Pressing and
// dragging a row emits ``rowDragBegun`` (the row), ``rowDragMoved`` (list coordinates),
// ``rowDragEnded`` and ``rowDragStarted`` with the ids to drag.
ListView {
    id: list

    // "compact" or "regular", see NavItem.
    property string size: "regular"
    property var selectedIds: []
    property string anchorId: ""
    // Off when the owner decides what a click selects (the Explorer tree, plan 132.3).
    property bool selectionEnabled: true
    // objectName of every row; empty gives "navRow_<id>".
    property string rowObjectName: ""
    // Ids of rows drawn with the accent colour (the open folder, the playing song).
    property var accentIds: []
    property var decorate: null
    readonly property int rowHeight: size === "compact" ? 28 : 52
    signal selectionUpdated()
    signal activated(string rowId)
    signal rowClicked(string rowId, int modifiers)
    signal rowDoubleClicked(string rowId)
    signal rowContextRequested(string rowId, real x, real y)
    signal rowChevronClicked(string rowId)
    signal rowRenamed(string rowId, string text)
    signal rowRenameCancelled(string rowId)
    signal rowDragBegun(string rowId)
    signal rowDragMoved(string rowId, real x, real y)
    signal rowDragEnded(string rowId)
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

    // The NavItem properties of one row: the row's own values, then ``decorate``.
    function describe(data) {
        const rowId = String(data.id)
        const base = {
            "title": String(data.title || data.name || ""),
            "subtitle": String(data.subtitle || ""),
            "leading": String(data.leading || ""),
            "tag": String(data.tag || ""),
            "tagTone": String(data.tagTone || "neutral"),
            "depth": Number(data.depth || 0),
            "expandable": data.expandable === true,
            "expanded": data.expanded === true,
            "dropTarget": data.dropTarget === true,
            "renaming": data.renaming === true,
            "accent": accentIds.indexOf(rowId) >= 0,
            "muted": false,
            "trailing": "",
            "trailingTone": "muted",
            "covers": [],
            "tileGradient": false
        }
        const extra = list.decorate ? list.decorate(data) : null
        return extra ? Object.assign(base, extra) : base
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
        if (!list.selectionEnabled)
            return
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
        required property var modelData
        readonly property var rowData: list.rowAt(index) || modelData || ({})
        readonly property string rowId: String(rowData.id)
        readonly property var nav: list.describe(rowData)

        width: list.width
        size: list.size
        height: list.rowHeight
        leading: nav.leading
        title: nav.title
        subtitle: nav.subtitle
        tag: nav.tag
        tagTone: nav.tagTone
        depth: nav.depth
        expandable: nav.expandable
        expanded: nav.expanded
        dropTarget: nav.dropTarget
        renaming: nav.renaming
        accent: nav.accent
        muted: nav.muted
        trailingText: nav.trailing
        trailingTone: nav.trailingTone
        covers: nav.covers || []
        tileGradient: nav.tileGradient === true
        selected: list.isSelected(rowId)
        objectName: list.rowObjectName.length > 0 ? list.rowObjectName : "navRow_" + rowId

        onClicked: (modifiers) => {
            list.forceActiveFocus()
            if (list.selectionEnabled)
                list.select(row.index, modifiers)
            list.rowClicked(row.rowId, modifiers)
        }
        onDoubleClicked: list.rowDoubleClicked(row.rowId)
        onContextRequested: (x, y) => {
            const point = row.mapToItem(list, x, y)
            if (list.selectionEnabled && !row.selected)
                list.select(row.index, 0)
            list.rowContextRequested(row.rowId, point.x, point.y)
        }
        onChevronClicked: list.rowChevronClicked(row.rowId)
        onRenamed: (text) => list.rowRenamed(row.rowId, text)
        onRenameCancelled: list.rowRenameCancelled(row.rowId)
        onDragStarted: {
            list.rowDragBegun(row.rowId)
            if (list.selectionEnabled && !row.selected)
                list.select(row.index, 0)
            list.rowDragStarted(list.selectedIds)
        }
        onDragMoved: (x, y) => {
            const point = row.mapToItem(list, x, y)
            list.rowDragMoved(row.rowId, point.x, point.y)
        }
        onDragEnded: list.rowDragEnded(row.rowId)
    }
}
