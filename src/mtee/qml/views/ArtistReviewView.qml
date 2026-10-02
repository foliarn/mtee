import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../components"

// One step of the artist identification: a list that fills the page, a local search,
// a button that confirms exactly the tracks of the current filter, and Edit.
Rectangle {
    id: page

    required property var workspace
    property var tab: null
    property int bottomInset: 0
    readonly property var manager: workspace.artistManager
    readonly property string view: tab && tab.id ? tab.id.substring(tab.id.indexOf(":") + 1) : ""
    readonly property string category: view.split(".")[0]
    readonly property string kind: view.split(".")[1] || "tracks"
    readonly property var listModel: manager.available && view.length > 0 ? manager.listModel(view) : null
    readonly property var status: manager.state
    readonly property var info: (status.categories || ({}))[category] || ({})
    readonly property bool locked: info.accessible === false
    readonly property int padding: width < 600 ? 12 : 24
    readonly property int confirmCount: listModel ? (kind === "artists" ? listModel.trackTotal : listModel.count) : 0
    readonly property string searchText: listModel ? listModel.searchText : ""
    readonly property var titles: ({
        "from_tags": "From tags",
        "suggested": "Suggested",
        "needs_input": "Needs input"
    })
    readonly property var subtitles: ({
        "from_tags": "Artists read from the file tags. Check them, then confirm.",
        "suggested": "Artists guessed from the file names and the remix titles. Check them, then confirm.",
        "needs_input": "Nothing usable was found. Add the artists with Edit, then confirm."
    })
    readonly property string previousLabel: category === "suggested" ? "From tags" : "Suggested"

    objectName: "artistReviewView"
    color: Theme.editor

    Connections {
        target: page.manager
        function onConfirmationReady(preview) { confirmDialog.show(preview) }
    }

    // Heading, search and the confirm button.
    Item {
        id: head
        x: page.padding
        width: parent.width - 2 * page.padding
        height: 112

        Column {
            anchors.left: parent.left
            anchors.right: toolbar.left
            anchors.rightMargin: 12
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12
            spacing: 2

            SectionLabel { text: "Identification" }

            Row {
                spacing: 12

                Text {
                    objectName: "artistReviewTitle"
                    text: page.titles[page.category] + " · " + (page.kind === "artists" ? "Artists" : "Tracks")
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                }

                Text {
                    topPadding: 12
                    text: page.listModel ? page.listModel.totalCount === page.listModel.count
                        ? page.listModel.count : page.listModel.count + " of " + page.listModel.totalCount : ""
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }
            }

            Text {
                width: parent.width
                text: page.subtitles[page.category] || ""
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }

        Row {
            id: toolbar
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12
            spacing: 8

            TextField {
                id: search
                objectName: "artistReviewSearch"
                width: Math.min(220, page.width * 0.25)
                height: 32
                text: page.searchText
                placeholderText: page.kind === "artists" ? "Search artists" : "Search tracks"
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                background: Rectangle {
                    color: Theme.surface
                    border.color: search.activeFocus ? Theme.focus : Theme.separator
                }
                onTextEdited: if (page.listModel) page.listModel.setSearch(text)
            }

            TextButton {
                objectName: "artistConfirmButton"
                text: "Confirm " + page.confirmCount + (page.confirmCount === 1 ? " track" : " tracks")
                kind: "primary"
                enabledAction: page.confirmCount > 0 && !page.locked && !page.manager.applying
                tip: page.manager.applying ? "Wait for the current application to finish." : ""
                onClicked: page.manager.requestConfirmation(page.category, page.kind, page.searchText)
            }

            IconButton {
                id: moreButton
                objectName: "artistMoreButton"
                width: 32
                height: 32
                icon: "more"
                iconSize: 18
                tip: "More"
                onClicked: moreMenu.popup(moreButton, 0, moreButton.height)
            }
        }
    }

    AppMenu {
        id: moreMenu
        implicitWidth: 240
        AppMenuItem { text: "Analyze collection again"; enabled: !page.manager.analyzing; onTriggered: page.manager.analyzeCollection() }
        AppMenuItem { text: "Retry unfinished files"; enabled: page.status.unfinishedApplications > 0 && !page.manager.applying; onTriggered: page.manager.retryUnfinished() }
        AppMenuSeparator {}
        AppMenuItem { text: "Undo the last confirmation"; enabled: !page.manager.applying; onTriggered: page.manager.undoLast() }
    }

    Rectangle {
        id: banner
        visible: !page.locked && page.status.unfinishedApplications > 0 && !page.manager.applying
        anchors.top: head.bottom
        x: page.padding
        width: parent.width - 2 * page.padding
        height: visible ? 36 : 0
        color: Theme.surface

        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 12
            width: parent.width - 120
            text: page.status.unfinishedApplications
                + " confirmed tracks are not applied to their files yet. The Tasks page lists the causes."
            elide: Text.ElideRight
            color: Theme.warning
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        TextButton {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            implicitHeight: 26
            text: "Retry"
            kind: "neutral"
            onClicked: page.manager.retryUnfinished()
        }
    }

    Item {
        id: body
        anchors.top: banner.visible ? banner.bottom : head.bottom
        anchors.topMargin: banner.visible ? 8 : 0
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom

        Loader {
            anchors.fill: parent
            active: page.listModel !== null && !page.locked
            sourceComponent: page.kind === "artists" ? artistsComponent : tracksComponent
        }

        Component {
            id: tracksComponent

            ArtistReviewTrackList {
                listModel: page.listModel
                bottomInset: page.bottomInset
                onEditRequested: trackId => editDialog.show(trackId)
                onArtistClicked: name => {
                    page.listModel.setSearch(name)
                    search.text = name
                }
            }
        }

        Component {
            id: artistsComponent

            ArtistListView {
                listModel: page.listModel
                bottomInset: page.bottomInset
                onArtistClicked: name => {
                    const tracks = page.manager.listModel(page.category + ".tracks")
                    tracks.setSearch(name)
                    page.workspace.openArtistView(page.category + ".tracks",
                        page.titles[page.category] + " · Tracks")
                }
                onActionRequested: (action, artistId, name) => actionDialog.show(action, artistId, name)
            }
        }

        // States that replace the list.
        Column {
            id: placeholder
            objectName: "artistReviewPlaceholder"
            anchors.centerIn: parent
            width: Math.min(420, parent.width - 48)
            spacing: 12
            visible: page.locked || !page.manager.available
                || (page.listModel !== null && page.listModel.count === 0)

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
                text: {
                    if (!page.manager.available)
                        return "Not available in the demo"
                    if (page.locked)
                        return "Finish " + page.previousLabel + " first"
                    if (!page.status.cohortRegistered)
                        return "Your collection has not been analyzed yet"
                    if (page.manager.analyzing && page.listModel.totalCount === 0)
                        return "Analysis in progress"
                    if (page.listModel.totalCount > 0 && page.searchText.length > 0)
                        return "No result for “" + page.searchText + "”"
                    if (!page.status.cohortReady)
                        return "Some tracks are not identified yet"
                    return "Nothing left in " + page.titles[page.category]
                }
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                text: {
                    if (!page.manager.available)
                        return "The artist manager works on your own library."
                    if (page.locked)
                        return "The steps are done in order the first time: "
                            + page.previousLabel + " has "
                            + ((page.status.categories[page.previousLabel === "From tags" ? "from_tags" : "suggested"] || {}).remaining || 0)
                            + " tracks left."
                    if (!page.status.cohortRegistered)
                        return "MTEE reads the tags and file names once, proposes the artists and renames nothing until you confirm."
                    if (page.manager.analyzing && page.listModel.totalCount === 0)
                        return "Results appear here as they arrive."
                    if (page.listModel.totalCount > 0 && page.searchText.length > 0)
                        return "Clear the search to see the other tracks."
                    if (!page.status.cohortReady)
                        return page.status.cohortMissing + " tracks could not be read. Analyze again to retry them."
                    return page.info.complete ? "This step is finished." : ""
                }
            }

            TextButton {
                objectName: "artistPlaceholderAction"
                anchors.horizontalCenter: parent.horizontalCenter
                visible: page.manager.available && !page.manager.analyzing
                    && (page.locked || !page.status.cohortRegistered || !page.status.cohortReady)
                text: page.locked ? "Open " + page.previousLabel
                    : page.status.cohortRegistered ? "Analyze again" : "Analyze collection"
                kind: "primary"
                onClicked: {
                    if (page.locked) {
                        const previous = page.category === "suggested" ? "from_tags" : "suggested"
                        page.workspace.openArtistView(previous + ".tracks", page.previousLabel + " · Tracks")
                    } else {
                        page.manager.analyzeCollection()
                    }
                }
            }
        }
    }

    ArtistEditDialog {
        id: editDialog
        manager: page.manager
        parent: Overlay.overlay
    }

    ArtistConfirmDialog {
        id: confirmDialog
        manager: page.manager
        parent: Overlay.overlay
    }

    ArtistActionDialog {
        id: actionDialog
        manager: page.manager
        parent: Overlay.overlay
    }
}
