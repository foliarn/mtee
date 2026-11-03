import QtQuick

// A ghost icon button that steps through ``options`` on each click (plan 130). An option is
// {key, label, icon}. The tooltip shows the current label; ``chosen`` carries the new key.
Item {
    id: cycle

    property var options: []
    property string currentKey: options.length > 0 ? options[0].key : ""
    readonly property int currentIndex: {
        for (let i = 0; i < options.length; ++i) {
            if (options[i].key === currentKey)
                return i
        }
        return options.length > 0 ? 0 : -1
    }
    readonly property var current: currentIndex >= 0 ? options[currentIndex] : null
    property int iconSize: 18
    signal chosen(string key)

    implicitWidth: 32
    implicitHeight: 32

    function step() {
        if (options.length === 0)
            return
        const next = options[(currentIndex + 1) % options.length]
        currentKey = next.key
        chosen(next.key)
    }

    IconButton {
        objectName: "cycleButtonInner"
        anchors.fill: parent
        icon: cycle.current ? (cycle.current.icon || "") : ""
        iconSize: cycle.iconSize
        tip: cycle.current ? cycle.current.label : ""
        onClicked: cycle.step()
    }
}
