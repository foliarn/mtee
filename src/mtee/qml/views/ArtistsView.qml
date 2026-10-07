import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../components"

// Catalog of the artists confirmed in the artist manager: number, placeholder
// thumbnail, name and number of tracks. A click opens the page of the artist, a right
// click offers Rename, Merge into… and Delete artist.
Rectangle {
    id: page

    required property var workspace
    property int bottomInset: 0
    readonly property var manager: workspace.artistManager
    readonly property var catalog: manager.available ? manager.listModel("catalog") : null
    readonly property int padding: width < 600 ? 12 : 24
    readonly property int typeWidth: width < 760 ? 0 : 190
    property var menuArtist: ({ "artistId": "", "name": "", "hidden": false })

    objectName: "artistsView"
    color: Theme.editor

    Item {
        id: head
        x: page.padding
        width: parent.width - 2 * page.padding
        height: 92

        Column {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 14
            spacing: 2

            SectionLabel { text: "Artists" }

            Row {
                spacing: 14

                Text {
                    id: titleText
                    objectName: "artistsTitle"
                    text: "Artists"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                }

                Text {
                    anchors.baseline: titleText.baseline
                    text: page.catalog ? page.catalog.count + (page.catalog.count === 1 ? " artist" : " artists") : ""
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }
    }

    TextField {
        id: searchField
        objectName: "artistsSearchField"
        visible: page.catalog !== null && typeof page.catalog.setSearch === "function"
        anchors.top: parent.top
        anchors.topMargin: 14
        anchors.right: parent.right
        anchors.rightMargin: page.padding
        width: Math.min(260, parent.width * 0.4)
        height: 28
        placeholderText: "Search artists"
        text: page.catalog ? page.catalog.searchText : ""
        selectByMouse: true
        color: Theme.textPrimary
        placeholderTextColor: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
        onTextEdited: page.catalog.setSearch(text)
        Keys.onEscapePressed: event => {
            text = ""
            page.catalog.setSearch("")
            event.accepted = true
        }
        background: Rectangle {
            color: Theme.surface
            border.width: 1
            border.color: searchField.activeFocus ? Theme.focus : Theme.separator
        }
    }

    // Filters: types (any of the chosen ones), a minimum number of tracks, hidden artists.
    Item {
        id: filterBar
        objectName: "artistsFilters"
        visible: page.catalog !== null && typeof page.catalog.toggleType === "function"
        anchors.top: head.bottom
        x: page.padding
        width: parent.width - 2 * page.padding
        height: visible ? filterFlow.implicitHeight + 10 : 0

        Flow {
            id: filterFlow
            width: parent.width
            spacing: 6

            Repeater {
                model: ["Producer", "DJ", "Singer", "MC", "No role"]

                delegate: FilterChip {
                    required property string modelData
                    objectName: "artistsType" + modelData.replace(" ", "")
                    text: modelData
                    checked: page.catalog !== null && page.catalog.types.indexOf(modelData) >= 0
                    onToggled: page.catalog.toggleType(modelData)
                }
            }

            TextField {
                id: minTracksField
                objectName: "artistsMinTracks"
                width: 110
                height: 26
                placeholderText: "Min tracks"
                text: page.catalog && page.catalog.minTracks > 0 ? String(page.catalog.minTracks) : ""
                validator: IntValidator { bottom: 0; top: 99999 }
                inputMethodHints: Qt.ImhDigitsOnly
                selectByMouse: true
                leftPadding: 10
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                onTextEdited: page.catalog.setMinTracks(text.length > 0 ? parseInt(text) : 0)
                background: Rectangle {
                    color: Theme.surface
                    border.width: 1
                    border.color: minTracksField.activeFocus ? Theme.focus : Theme.separator
                }
            }

            Row {
                height: 26
                spacing: 8
                leftPadding: 8

                ToggleSwitch {
                    objectName: "artistsShowHidden"
                    anchors.verticalCenter: parent.verticalCenter
                    checked: page.manager.showHidden
                    onToggled: (value) => page.manager.setShowHidden(value)
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Show hidden artists"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            TextButton {
                objectName: "artistsClearFilters"
                visible: page.catalog !== null && page.catalog.filtered
                height: 26
                text: "Clear filters"
                kind: "ghost"
                onClicked: page.catalog.clearFilters()
            }
        }
    }

    Row {
        id: columns
        anchors.top: filterBar.bottom
        x: page.padding
        width: parent.width - 2 * page.padding
        height: 30

        Text {
            width: 48
            anchors.verticalCenter: parent.verticalCenter
            text: "#"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
        }

        Text {
            width: parent.width - 48 - 110 - page.typeWidth
            anchors.verticalCenter: parent.verticalCenter
            text: "Artist"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
        }

        Text {
            width: page.typeWidth
            visible: page.typeWidth > 0
            anchors.verticalCenter: parent.verticalCenter
            text: "Type"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
        }

        Text {
            width: 110
            anchors.verticalCenter: parent.verticalCenter
            text: "Tracks"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
        }
    }

    Rectangle {
        id: rule
        anchors.top: columns.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.separator
    }

    ListView {
        id: list
        objectName: "artistCatalogList"
        anchors.top: rule.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: page.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.catalog
        ScrollBar.vertical: ThinScrollBar {}

        WheelScrollHandler {
            flickable: list
            speed: 4
        }

        delegate: Rectangle {
            id: row

            required property int index
            required property string artistId
            required property string name
            required property int tracks
            required property var roles
            required property bool hidden
            required property bool unavailable

            width: ListView.view.width
            height: Theme.rowHeight
            color: hit.containsMouse ? Theme.surface : "transparent"

            Text {
                x: page.padding
                width: 48
                anchors.verticalCenter: parent.verticalCenter
                text: row.index + 1
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            PlaylistCover {
                id: thumb
                x: page.padding + 48 - 16
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.coverSize
                height: Theme.coverSize
                source: ""
                covers: []
            }

            Text {
                x: thumb.x + thumb.width + 14
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - x - 110 - page.typeWidth - page.padding
                text: row.name
                elide: Text.ElideRight
                color: row.hidden ? Theme.textMuted : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                x: parent.width - page.padding - 110 - page.typeWidth
                width: page.typeWidth - 12
                visible: page.typeWidth > 0
                anchors.verticalCenter: parent.verticalCenter
                text: (row.roles.length > 0 ? row.roles.join(" · ") : "No role") + (row.hidden ? " · hidden" : "")
                elide: Text.ElideRight
                color: Theme.textSecondary
                opacity: row.roles.length > 0 ? 1 : 0.6
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Text {
                x: parent.width - page.padding - 110
                anchors.verticalCenter: parent.verticalCenter
                text: row.tracks
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            MouseArea {
                id: hit
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: Qt.PointingHandCursor
                onClicked: event => {
                    if (event.button === Qt.RightButton) {
                        page.menuArtist = { "artistId": row.artistId, "name": row.name, "hidden": row.hidden }
                        menu.popup(row, event.x, event.y)
                    } else {
                        page.workspace.openArtistPage(row.artistId, row.name)
                    }
                }
            }
        }

        Column {
            objectName: "artistsEmpty"
            anchors.centerIn: parent
            width: Math.min(420, parent.width - 48)
            spacing: 8
            visible: page.catalog !== null && page.catalog.count === 0

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: page.catalog && (page.catalog.searchText || page.catalog.filtered) ? "No matching artist" : "No artist yet"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.Bold
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: page.catalog && (page.catalog.searchText || page.catalog.filtered)
                    ? "Try another name or clear the filters."
                    : "Artists appear here once their tracks are confirmed in the Artist manager."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
        }
    }

    AppMenu {
        id: menu
        implicitWidth: 180
        AppMenuItem { text: "Open"; onTriggered: page.workspace.openArtistPage(page.menuArtist.artistId, page.menuArtist.name) }
        AppMenuItem { text: "Edit profile…"; onTriggered: profileDialog.show(page.menuArtist.artistId, page.menuArtist.name) }
        AppMenuItem {
            text: page.menuArtist.hidden ? "Show artist" : "Hide artist (idgaf)"
            onTriggered: page.manager.setArtistHidden(page.menuArtist.artistId, !page.menuArtist.hidden)
        }
        AppMenuSeparator {}
        AppMenuItem { text: "Rename"; onTriggered: actionDialog.show("rename", page.menuArtist.artistId, page.menuArtist.name) }
        AppMenuItem { text: "Merge into…"; onTriggered: actionDialog.show("merge", page.menuArtist.artistId, page.menuArtist.name) }
        AppMenuSeparator {}
        AppMenuItem { text: "Delete artist"; onTriggered: actionDialog.show("delete", page.menuArtist.artistId, page.menuArtist.name) }
    }

    ArtistProfileDialog {
        id: profileDialog
        manager: page.manager
        parent: Overlay.overlay
    }

    ArtistActionDialog {
        id: actionDialog
        manager: page.manager
        parent: Overlay.overlay
    }
}
