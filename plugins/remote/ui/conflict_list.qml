import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Every conflict of MTEE Remote that waits, as a tab of a center window (review of 0.3.0). The bell
// and the Remote window show the oldest ones and a row that opens this list. The list is a
// ListView: only the rows in view are drawn, so thousands of conflicts after a first match stay
// cheap. A click opens the conflict's own tab. The core sets workspace, tab, groupId, groupIndex,
// bottomInset and backend after loading.
Rectangle {
    id: page

    property var workspace
    property var tab
    property string groupId: ""
    property int groupIndex: 0
    property int bottomInset: 0
    property var backend
    readonly property var rows: page.backend ? page.backend.rows : []
    readonly property bool loading: page.backend ? page.backend.loading : false

    objectName: "conflictList"
    color: Theme.editor

    // The backend may come as an initial property (no change signal) or later: ask in both cases.
    Component.onCompleted: if (page.backend) page.backend.load()
    onBackendChanged: if (page.backend) page.backend.load()

    Column {
        id: heading
        x: Math.max(24, (page.width - width) / 2)
        y: 30
        width: Math.min(900, page.width - 48)
        spacing: 2

        SectionLabel { text: "Remote" }

        Text {
            width: parent.width
            text: "Conflicts"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeHeading
            font.weight: Font.Bold
        }

        Text {
            objectName: "conflictListCount"
            width: parent.width
            text: page.loading && page.rows.length === 0 ? "Reading the conflicts…"
                : page.rows.length === 0 ? "Nothing waits for you."
                : page.rows.length.toLocaleString(Qt.locale(), "f", 0)
                    + (page.rows.length === 1 ? " conflict waits" : " conflicts wait")
                    + " for you. Open one to choose what to keep."
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }
    }

    ListView {
        id: list
        objectName: "conflictListView"
        anchors.top: heading.bottom
        anchors.topMargin: 16
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.bottomInset
        x: heading.x
        width: heading.width
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.rows
        WheelScrollHandler { flickable: list }
        ScrollBar.vertical: ThinScrollBar {}

        delegate: NavItem {
            required property var modelData
            objectName: "conflictListRow"
            width: list.width
            size: "regular"
            leading: "alert"
            title: modelData.title
            subtitle: modelData.subtitle
            onClicked: page.backend.open(modelData.id)
        }
    }
}
