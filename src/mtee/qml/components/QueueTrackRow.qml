import QtQuick
import Mtee

// One track line shared by the fullscreen queue card, the Queue panel and the History
// panel: cover with a veil and a play/pause icon, title, artist and a "…" button. The
// owner decides what a click, a double click, a drag and the menu do.
Item {
    id: row

    required property var rowData
    property string entryId: String(rowData.entryId || "")
    property bool current: false
    property bool playing: false
    property bool dragging: false
    property bool dropBefore: false
    property string timeText: ""
    property int horizontalPadding: 6
    property int rightPadding: 14
    readonly property bool available: rowData.available !== false
    readonly property bool hovered: rowMouse.containsMouse || coverMouse.containsMouse
        || moreMouse.containsMouse

    signal coverClicked()
    signal rowDoubleClicked()
    signal menuRequested(var anchor, real x, real y)
    signal pressedAt(var row, real x, real y, int button)
    signal movedTo(var row, real x, real y, int buttons)
    signal released()
    signal canceled()

    objectName: current ? "queueCurrentRow" : "queueRow_" + entryId
    height: 56

    Rectangle {
        anchors.fill: parent
        anchors.rightMargin: 8
        color: row.dragging || row.hovered ? Theme.selection : "transparent"
        opacity: row.available ? 1 : 0.6
    }

    Rectangle {
        visible: row.dropBefore && !row.current
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 3
        color: Theme.primary
    }

    MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: (event) => {
            if (event.button === Qt.RightButton)
                row.menuRequested(row, event.x, event.y)
            else
                row.pressedAt(row, event.x, event.y, event.button)
        }
        onPositionChanged: (event) => row.movedTo(row, event.x, event.y, event.buttons)
        onReleased: row.released()
        onCanceled: row.canceled()
        onDoubleClicked: row.rowDoubleClicked()
    }

    CoverArt {
        id: cover
        x: row.horizontalPadding
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.coverSize + 4
        height: width
        opacity: row.available ? 1 : 0.5
        pattern: row.rowData.cover !== undefined ? row.rowData.cover : -1
        source: row.rowData.coverUrl || ""

        Rectangle {
            anchors.fill: parent
            color: "#000000"
            opacity: row.available && (row.current || row.hovered) ? 0.45 : 0

            Behavior on opacity { NumberAnimation { duration: 120 } }
        }

        Icon {
            objectName: "queueCoverIcon"
            anchors.centerIn: parent
            name: row.current && row.playing ? "pause" : "play"
            size: 18
            color: "#FFFFFF"
            opacity: row.available && (row.current || row.hovered) ? 1 : 0

            Behavior on opacity { NumberAnimation { duration: 120 } }
        }

        MouseArea {
            id: coverMouse
            objectName: "queueCoverButton"
            anchors.fill: parent
            hoverEnabled: true
            enabled: row.available
            cursorShape: Qt.PointingHandCursor
            onClicked: row.coverClicked()
        }
    }

    Column {
        anchors.left: cover.right
        anchors.leftMargin: 12
        anchors.right: trailing.left
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        Text {
            objectName: "queueRowTitle"
            width: parent.width
            text: row.rowData.title || row.rowData.filename || "Unknown track"
            elide: Text.ElideRight
            color: row.current ? Theme.primary : row.available ? Theme.textPrimary : Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeBody
        }

        Text {
            width: parent.width
            text: row.available ? (row.rowData.artist || "Unknown artist") : "Unavailable"
            elide: Text.ElideRight
            color: row.available ? Theme.textSecondary : Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    // The time of a listening shows at rest and gives way to the "…" button on hover.
    Item {
        id: trailing
        objectName: "queueRowMore"
        anchors.right: parent.right
        anchors.rightMargin: row.rightPadding
        anchors.verticalCenter: parent.verticalCenter
        width: row.timeText.length > 0 ? 74 : 28
        height: 28

        Text {
            objectName: "queueRowTime"
            visible: row.timeText.length > 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: row.timeText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            opacity: row.hovered ? 0 : 1
        }

        Icon {
            anchors.right: parent.right
            anchors.rightMargin: 5
            anchors.verticalCenter: parent.verticalCenter
            name: "more"
            size: 18
            color: moreMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
            opacity: row.hovered ? 1 : 0
        }

        MouseArea {
            id: moreMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: row.menuRequested(trailing, 0, 28)
        }
    }
}
