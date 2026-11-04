import QtQuick
import Mtee

// The centre tree of the windows (plan 131.7). A leaf is one centre window (EditorGroup); a split lays
// its children along its axis by ratio, with a SplitHandle in each gap. A handle drag sends the new
// shares back through ``setSplitRatios``, and no window goes under its minimum size. ``node`` is the
// node drawn here (read from ``workspace.centerLayout``) and ``path`` its child indexes from the root.
Item {
    id: tree

    // Null until the parent sets it; a leaf is not built before then.
    property var workspace: null
    property var node: ({ "type": "leaf", "group": "" })
    property var path: []
    property bool singleGroup: false
    property int bottomInset: 0

    readonly property bool isSplit: node.type === "split"
    readonly property bool rowSplit: isSplit && node.orientation === "row"
    readonly property int childCount: isSplit ? node.children.length : 0
    readonly property real axisLength: rowSplit ? width : height
    readonly property int gap: Theme.windowGap
    readonly property var groupList: workspace ? workspace.groups : []
    readonly property string leafId: isSplit ? "" : String(node.group || "")
    readonly property int groupIndex: indexOfGroup(leafId)
    readonly property var groupData: groupIndex >= 0 ? groupList[groupIndex]
        : ({ "id": leafId, "tabs": [], "active": "" })

    // Resize state: the child lengths in pixels when a handle drag starts.
    property var resizeStart: []

    function indexOfGroup(groupId) {
        for (let i = 0; i < groupList.length; i++) {
            if (groupList[i].id === groupId)
                return i
        }
        return -1
    }

    // The pixel length of child ``index`` along the split's axis.
    function lengthOf(index) {
        if (!isSplit)
            return 0
        return Math.max(0, (axisLength - gap * (childCount - 1)) * node.ratios[index])
    }

    // The offset of child ``index`` along the split's axis, measured from the start of the split.
    function offsetOf(index) {
        let offset = 0
        for (let i = 0; i < index; i++)
            offset += lengthOf(i) + gap
        return offset
    }

    // The shortest length of ``item`` along the row axis (alongRow) or the column axis: a leaf needs
    // its minimum window size; children of a split along that axis add up, other children take the max.
    function minimumLength(item, alongRow) {
        if (item.type !== "split")
            return alongRow ? Theme.minCenterWindowWidth : Theme.minCenterWindowHeight
        const parts = item.children.map(child => minimumLength(child, alongRow))
        if ((item.orientation === "row") === alongRow)
            return parts.reduce((sum, part) => sum + part, 0) + gap * (parts.length - 1)
        return Math.max(...parts)
    }

    function beginResize() {
        const lengths = []
        for (let i = 0; i < childCount; i++)
            lengths.push(lengthOf(i))
        resizeStart = lengths
    }

    // Move the gap after child ``index`` by ``distance`` pixels; both neighbours keep their minimum.
    function resizeAt(index, distance) {
        if (resizeStart.length !== childCount)
            return
        const lengths = resizeStart.slice()
        const pair = lengths[index] + lengths[index + 1]
        const low = minimumLength(node.children[index], rowSplit)
        const high = pair - minimumLength(node.children[index + 1], rowSplit)
        const first = Math.min(Math.max(lengths[index] + distance, low), Math.max(low, high))
        lengths[index] = first
        lengths[index + 1] = pair - first
        const total = lengths.reduce((sum, value) => sum + value, 0)
        if (total <= 0)
            return
        workspace.setSplitRatios(path, lengths.map(value => value / total))
    }

    // The centre window with ``groupId`` in this tree, or null.
    function groupItem(groupId) {
        if (leaf.item && leaf.item.groupId === groupId)
            return leaf.item
        for (let i = 0; i < branches.count; i++) {
            const child = branches.itemAt(i)
            const found = child && child.item ? child.item.groupItem(groupId) : null
            if (found)
                return found
        }
        return null
    }

    // The children of a split, each one a tree of its own: this file loaded again for each child.
    // The bindings are set once the child exists, and the workspace last, so that no leaf is built
    // from an empty node.
    Repeater {
        id: branches
        model: tree.childCount

        delegate: Loader {
            id: branch
            required property int index

            x: tree.rowSplit ? tree.offsetOf(index) : 0
            y: tree.rowSplit ? 0 : tree.offsetOf(index)
            width: tree.rowSplit ? tree.lengthOf(index) : tree.width
            height: tree.rowSplit ? tree.height : tree.lengthOf(index)
            source: "WindowTree.qml"
            onLoaded: {
                item.node = Qt.binding(() => tree.node.children[branch.index])
                item.path = Qt.binding(() => tree.path.concat([branch.index]))
                item.singleGroup = Qt.binding(() => tree.singleGroup)
                item.bottomInset = Qt.binding(() => tree.bottomInset)
                item.width = Qt.binding(() => branch.width)
                item.height = Qt.binding(() => branch.height)
                item.workspace = Qt.binding(() => tree.workspace)
            }
        }
    }

    // One handle in each gap between two children; drawn above them.
    Repeater {
        model: tree.isSplit ? tree.childCount - 1 : 0

        delegate: SplitHandle {
            required property int index

            orientation: tree.rowSplit ? Qt.Horizontal : Qt.Vertical
            x: tree.rowSplit ? tree.offsetOf(index) + tree.lengthOf(index) + tree.gap / 2 - width / 2 : 0
            y: tree.rowSplit ? 0 : tree.offsetOf(index) + tree.lengthOf(index) + tree.gap / 2 - height / 2
            width: tree.rowSplit ? implicitWidth : tree.width
            height: tree.rowSplit ? tree.height : implicitHeight
            onDragStarted: tree.beginResize()
            onDragged: (delta) => tree.resizeAt(index, delta)
        }
    }

    // A leaf is one centre window.
    Loader {
        id: leaf
        anchors.fill: parent
        active: !tree.isSplit && tree.workspace !== null
        sourceComponent: groupComponent
    }

    Component {
        id: groupComponent

        EditorGroup {
            anchors.fill: parent
            workspace: tree.workspace
            groupId: tree.leafId
            groupIndex: tree.groupIndex
            groupData: tree.groupData
            groupCount: tree.groupList.length
            singleGroup: tree.singleGroup
            bottomInset: tree.bottomInset
        }
    }
}
