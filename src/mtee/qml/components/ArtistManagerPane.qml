import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Sidebar of the artist manager: the identification steps as a tree, the state of the
// analysis of the collection and the way back to unfinished applications.
Item {
    id: pane

    required property var workspace
    readonly property var manager: workspace.artistManager
    readonly property bool live: manager.available
    readonly property var status: manager.state
    readonly property var categories: status.categories || ({})
    readonly property string activeTabId: workspace.groups.length > 0
        ? workspace.groups[workspace.activeGroup].active : ""
    property bool identificationOpen: true
    property bool artistsOpen: true
    readonly property var catalog: live ? manager.listModel("catalog") : null
    property var menuArtist: ({ "artistId": "", "name": "" })

    objectName: "artistManagerPane"

    readonly property var steps: [
        { "key": "from_tags", "label": "From tags", "views": ["tracks", "artists"] },
        { "key": "suggested", "label": "Suggested", "views": ["tracks", "artists"] },
        { "key": "needs_input", "label": "Needs input", "views": ["tracks"] }
    ]

    function previous(key) {
        return key === "suggested" ? "From tags" : key === "needs_input" ? "Suggested" : ""
    }

    function openStep(key, view, label) {
        workspace.openArtistView(key + "." + view, label + " · " + (view === "tracks" ? "Tracks" : "Artists"))
    }

    PaneHeader {
        id: header
        width: parent.width
        title: "Artist manager"
    }

    Flickable {
        id: scroller
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        contentHeight: content.implicitHeight + 16
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: content
            width: scroller.width

            Text {
                visible: !pane.live
                x: 16
                width: parent.width - 32
                topPadding: 8
                text: "The artist manager works on your own library. It is not available in the demo."
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            // State of the first pass and of the confirmations that did not finish.
            Column {
                id: stateBlock
                visible: pane.live
                x: 16
                width: parent.width - 32
                topPadding: 8
                bottomPadding: 10
                spacing: 8

                Text {
                    width: parent.width
                    visible: text.length > 0
                    text: {
                        if (pane.manager.analyzing)
                            return pane.status.cohortMissing > 0
                                ? "Identifying artists · " + pane.status.cohortMissing + " left"
                                : "Analyzing the collection…"
                        if (!pane.status.cohortRegistered)
                            return "The artists of your collection have not been identified yet."
                        if (pane.status.cohortMissing > 0)
                            return pane.status.cohortMissing + " tracks could not be identified."
                        if (pane.status.completed)
                            return "First pass complete. Everything is open."
                        return ""
                    }
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                TextButton {
                    objectName: "analyzeCollectionButton"
                    visible: !pane.manager.analyzing
                        && (!pane.status.cohortRegistered || pane.status.cohortMissing > 0)
                    text: pane.status.cohortRegistered ? "Analyze again" : "Analyze collection"
                    kind: "primary"
                    tip: "Reads the tags and file names of every track, once. Nothing is renamed or written."
                    onClicked: pane.manager.analyzeCollection()
                }

                Text {
                    width: parent.width
                    visible: pane.status.unfinishedApplications > 0 && !pane.manager.applying
                    text: pane.status.unfinishedApplications + " confirmed tracks are not applied to their files yet."
                    wrapMode: Text.Wrap
                    color: Theme.warning
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Row {
                    visible: pane.status.unfinishedApplications > 0 && !pane.manager.applying
                    spacing: 6

                    TextButton {
                        objectName: "retryApplicationsButton"
                        text: "Retry"
                        kind: "neutral"
                        onClicked: pane.manager.retryUnfinished()
                    }
                }
            }

            // Artists: the established profiles, alphabetical, in a scrolling list.
            TreeRow {
                objectName: "artistsTreeRow"
                visible: pane.live
                label: "Artists"
                chevron: pane.artistsOpen ? "chevron-down" : "chevron-right"
                strong: true
                count: pane.catalog ? pane.catalog.count : 0
                current: pane.activeTabId === "artists:catalog"
                onChevronActivated: pane.artistsOpen = !pane.artistsOpen
                onActivated: {
                    pane.artistsOpen = true
                    pane.workspace.openArtistView("catalog", "Artists")
                }
            }

            ListView {
                id: artistTree
                objectName: "artistTree"
                visible: pane.live && pane.artistsOpen && pane.catalog !== null && pane.catalog.count > 0
                width: content.width
                height: visible ? Math.min(pane.catalog.count, 10) * Theme.treeRowHeight : 0
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                model: pane.catalog
                ScrollBar.vertical: ThinScrollBar {}

                delegate: TreeRow {
                    id: node
                    required property string artistId
                    required property string name
                    width: ListView.view.width
                    height: Theme.treeRowHeight
                    depth: 1
                    label: name
                    current: pane.activeTabId === "artist:" + artistId
                    onActivated: pane.workspace.openArtistPage(artistId, name)
                    onContext: (x, y) => {
                        pane.menuArtist = { "artistId": artistId, "name": name }
                        artistMenu.popup(node, x, y)
                    }
                }
            }

            Text {
                visible: pane.live && pane.artistsOpen && pane.catalog !== null && pane.catalog.count === 0
                x: 28
                width: parent.width - 44
                bottomPadding: 6
                text: "Confirmed artists appear here."
                wrapMode: Text.Wrap
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeCaption
            }

            // Identification: three steps done in order the first time.
            TreeRow {
                visible: pane.live
                label: "Identification"
                chevron: pane.identificationOpen ? "chevron-down" : "chevron-right"
                strong: true
                onActivated: pane.identificationOpen = !pane.identificationOpen
            }

            Repeater {
                model: pane.live && pane.identificationOpen ? pane.steps : []

                delegate: Column {
                    id: step
                    required property var modelData
                    readonly property var info: pane.categories[modelData.key] || ({})
                    readonly property bool open: info.accessible === true

                    width: content.width

                    TreeRow {
                        depth: 1
                        label: step.modelData.label
                        count: step.info.remaining !== undefined ? step.info.remaining : 0
                        muted: !step.open
                        icon: step.info.complete === true ? "check" : ""
                    }

                    Text {
                        visible: !step.open
                        x: 44
                        width: parent.width - 56
                        bottomPadding: 4
                        text: "Finish " + pane.previous(step.modelData.key) + " first."
                        wrapMode: Text.Wrap
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }

                    Repeater {
                        model: step.modelData.views

                        delegate: TreeRow {
                            required property string modelData
                            depth: 2
                            label: modelData === "tracks" ? "Tracks" : "Artists"
                            muted: !step.open
                            current: pane.activeTabId === "artists:" + step.modelData.key + "." + modelData
                            onActivated: if (step.open) pane.openStep(step.modelData.key, modelData, step.modelData.label)
                        }
                    }
                }
            }
        }
    }

    component TreeRow: Rectangle {
        id: row

        property int depth: 0
        property string label: ""
        property string chevron: ""
        property string icon: ""
        property int count: -1
        property bool current: false
        property bool muted: false
        property bool strong: false
        signal activated()
        signal chevronActivated()
        signal context(real x, real y)

        width: parent ? parent.width : 0
        height: Theme.treeRowHeight + 4
        color: current ? Theme.selection : hit.containsMouse && !muted ? Theme.surface : "transparent"

        Icon {
            x: 12 + row.depth * 14
            anchors.verticalCenter: parent.verticalCenter
            visible: row.chevron.length > 0
            name: row.chevron
            size: 14
            color: Theme.textSecondary
        }

        Text {
            x: 12 + row.depth * 14 + (row.chevron.length > 0 ? 20 : 0)
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 56
            text: row.label
            elide: Text.ElideRight
            color: row.muted ? Theme.textMuted : row.current ? Theme.primary : Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
            font.weight: row.strong ? Font.DemiBold : Font.Normal
        }

        Icon {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            visible: row.icon.length > 0
            name: row.icon
            size: 14
            color: Theme.primary
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            visible: row.count > 0 && row.icon.length === 0
            text: row.count
            color: row.muted ? Theme.textMuted : Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        MouseArea {
            id: hit
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: row.muted ? Qt.ArrowCursor : Qt.PointingHandCursor
            onClicked: event => {
                if (event.button === Qt.RightButton)
                    row.context(event.x, event.y)
                else if (row.chevron.length > 0 && event.x < 12 + row.depth * 14 + 20)
                    row.chevronActivated()
                else
                    row.activated()
            }
        }
    }

    AppMenu {
        id: artistMenu
        implicitWidth: 180
        AppMenuItem { text: "Open"; onTriggered: pane.workspace.openArtistPage(pane.menuArtist.artistId, pane.menuArtist.name) }
        AppMenuSeparator {}
        AppMenuItem { text: "Rename"; onTriggered: actionDialog.show("rename", pane.menuArtist.artistId, pane.menuArtist.name) }
        AppMenuItem { text: "Merge into…"; onTriggered: actionDialog.show("merge", pane.menuArtist.artistId, pane.menuArtist.name) }
        AppMenuSeparator {}
        AppMenuItem { text: "Delete artist"; onTriggered: actionDialog.show("delete", pane.menuArtist.artistId, pane.menuArtist.name) }
    }

    ArtistActionDialog {
        id: actionDialog
        manager: pane.manager
        parent: Overlay.overlay
    }
}
