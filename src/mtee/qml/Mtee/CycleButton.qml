import QtQuick

// A ghost button that steps through ``options`` on each click (plan 130). An option is
// {key, label, icon}. The tooltip shows the current label; ``chosen`` carries the new key.
// ``labelled`` (plan 132.5) draws the current label as text instead of the icon.
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
    property bool labelled: false
    signal chosen(string key)

    implicitWidth: labelled ? labelText.implicitWidth + 16 : 32
    implicitHeight: labelled ? 24 : 32

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
        visible: !cycle.labelled
        icon: cycle.current ? (cycle.current.icon || "") : ""
        iconSize: cycle.iconSize
        tip: cycle.current ? cycle.current.label : ""
        onClicked: cycle.step()
    }

    Rectangle {
        anchors.fill: parent
        visible: cycle.labelled
        radius: Theme.radiusControl
        color: labelHit.containsMouse ? Theme.surface : "transparent"
    }

    Text {
        id: labelText
        objectName: "cycleButtonLabel"
        visible: cycle.labelled
        anchors.centerIn: parent
        text: cycle.current ? cycle.current.label : ""
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeCaption
    }

    MouseArea {
        id: labelHit
        anchors.fill: parent
        visible: cycle.labelled
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: cycle.step()
    }
}
