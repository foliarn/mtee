import QtQuick

// One row of a sidebar list (plan 130). ``leading`` is a cover URL (contains "://" or starts with
// "/"), a one-letter tile, or an icon name; it is drawn on a fixed square with ``radiusCover``.
// The hover and selection background is a rounded rectangle inset by 4 px on both sides, drawn
// only behind this row. ``size`` is "compact" (28 px, tree rows) or "regular" (52 px, 40 px tile).
Item {
    id: item

    property string size: "regular"
    property string leading: ""
    property string title: ""
    property string subtitle: ""
    property string tag: ""
    property string tagTone: "neutral"
    property int depth: 0
    property bool expandable: false
    property bool expanded: false
    property bool selected: false
    property bool renaming: false
    property bool dropTarget: false
    property bool keepExtension: false
    readonly property bool compact: size === "compact"
    readonly property bool hovered: mouse.containsMouse
    readonly property int tileSize: compact ? 18 : 40
    readonly property bool isCover: leading.indexOf("://") > 0 || leading.charAt(0) === "/"
    readonly property bool isLetter: !isCover && leading.length === 1
    property alias trailing: trailingRow.data
    signal clicked(int modifiers)
    signal doubleClicked()
    signal contextRequested(real x, real y)
    signal chevronClicked()
    signal renamed(string text)
    signal renameCancelled()
    signal dragStarted()

    implicitWidth: 240
    implicitHeight: compact ? 28 : 52

    Rectangle {
        objectName: "navItemBackground"
        x: 4
        width: parent.width - 8
        height: parent.height
        radius: Theme.radiusControl
        color: item.dropTarget ? Qt.rgba(0.776, 1, 0.102, 0.18)
            : item.selected ? Theme.selection
            : item.hovered ? Theme.surface : "transparent"
        border.width: item.dropTarget ? 1 : 0
        border.color: Theme.primary
    }

    MouseArea {
        id: mouse
        property real pressX: 0
        property real pressY: 0
        property bool dragSent: false
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: (event) => {
            pressX = event.x
            pressY = event.y
            dragSent = false
        }
        onPositionChanged: (event) => {
            if (pressed && !dragSent && (event.buttons & Qt.LeftButton)
                    && Math.abs(event.x - pressX) + Math.abs(event.y - pressY) > 10) {
                dragSent = true
                item.dragStarted()
            }
        }
        onClicked: (event) => {
            if (event.button === Qt.RightButton)
                item.contextRequested(event.x, event.y)
            else
                item.clicked(event.modifiers)
        }
        onDoubleClicked: (event) => {
            if (event.button === Qt.LeftButton)
                item.doubleClicked()
        }
    }

    Row {
        id: content
        x: 12 + item.depth * 16
        height: parent.height
        spacing: 8

        Item {
            id: chevronBox
            width: item.compact ? 14 : 0
            height: parent.height
            visible: item.compact || item.expandable

            Icon {
                anchors.centerIn: parent
                visible: item.expandable
                name: item.expanded ? "chevron-down" : "chevron-right"
                size: 12
                color: Theme.textMuted
            }
            MouseArea {
                anchors.fill: parent
                enabled: item.expandable
                onClicked: item.chevronClicked()
            }
        }

        Rectangle {
            id: tile
            objectName: "navItemLeading"
            visible: item.leading.length > 0
            anchors.verticalCenter: parent.verticalCenter
            width: item.tileSize
            height: item.tileSize
            radius: Theme.radiusCover
            color: item.isCover ? "transparent" : Theme.selection
            clip: true

            Image {
                anchors.fill: parent
                visible: item.isCover
                source: item.isCover ? item.leading : ""
                sourceSize: Qt.size(item.tileSize * 2, item.tileSize * 2)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
            }
            Text {
                anchors.centerIn: parent
                visible: item.isLetter
                text: item.leading.toUpperCase()
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: item.compact ? Theme.fontSizeSmall : Theme.fontSizeTitle
                font.weight: Font.DemiBold
            }
            Icon {
                anchors.centerIn: parent
                visible: !item.isCover && !item.isLetter
                name: item.isCover || item.isLetter ? "" : item.leading
                size: item.compact ? 14 : 20
                color: Theme.textSecondary
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(0, item.width - 24 - item.depth * 16
                - (chevronBox.visible ? chevronBox.width + content.spacing : 0)
                - (tile.visible ? tile.width + content.spacing : 0)
                - (trailingRow.width > 0 ? trailingRow.width + 8 : 0))
            spacing: 2

            Text {
                visible: !item.renaming
                width: parent.width
                text: item.title
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Row {
                visible: !item.compact && !item.renaming && (item.subtitle.length > 0 || item.tag.length > 0)
                width: parent.width
                spacing: 6
                TagChip {
                    visible: item.tag.length > 0
                    text: item.tag
                    tone: item.tagTone
                }
                Text {
                    visible: item.subtitle.length > 0
                    width: Math.max(0, parent.width - (item.tag.length > 0 ? 60 : 0))
                    text: item.subtitle
                    elide: Text.ElideRight
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
            InlineEdit {
                id: editor
                objectName: "navItemEditor"
                width: parent.width
                keepExtension: item.keepExtension
                onCommitted: (text) => { item.renaming = false; item.renamed(text) }
                onCancelled: { item.renaming = false; item.renameCancelled() }
            }
        }
    }

    Row {
        id: trailingRow
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 6
    }

    onRenamingChanged: {
        if (renaming)
            editor.begin(title)
        else
            editor.visible = false
    }
}
