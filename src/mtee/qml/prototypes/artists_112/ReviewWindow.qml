import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import Mtee

// Mock-up of the core Artists view (plan 112), isolated from Main.qml. Synthetic data only:
// the activity, the sidebar list, the artist page and the two override actions use the same
// Theme and components as the application. Play and Shuffle only report in this mock-up.
Window {
    id: root
    objectName: "artists112Review"
    width: Math.min(1440, Screen.desktopAvailableWidth - 32)
    height: Math.min(900, Screen.desktopAvailableHeight - 32)
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "MTEE — Artists review"
    color: Theme.chrome

    // "menu": the override actions sit in the page's "more" menu. "inline": two buttons.
    property string variant: "menu"
    // The credits this artist was cut from; a plain name is not "from" itself.
    readonly property var cutCredits: prototype.artistCredits.filter(
        credit => credit.toLowerCase() !== prototype.artistName.toLowerCase())
    readonly property string creditText: cutCredits.map(credit => "“" + credit + "”").join(", ")

    function quoted(list) { return list.map(credit => "“" + credit + "”").join(", ") }
    function openMenu() { actionsMenu.popup(moreButton, 0, moreButton.height) }

    // ------------------------------------------------------------ activity bar

    Rectangle {
        id: activity
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Theme.activityBarWidth
        color: Theme.chrome

        Column {
            anchors.top: parent.top
            width: parent.width
            ActivityIcon { icon: "explorer"; tip: "Explorer" }
            ActivityIcon { icon: "playlists"; tip: "Playlists" }
            ActivityIcon { icon: "convert"; tip: "Convert" }
            ActivityIcon { icon: "tasks"; tip: "Tasks" }
            ActivityIcon { objectName: "activityArtists"; icon: "artists"; tip: "Artists"; highlighted: true }
        }
        Column {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            width: parent.width
            ActivityIcon { icon: "settings"; tip: "Settings (Ctrl+,)" }
        }
    }

    // ------------------------------------------------------------ sidebar

    Rectangle {
        id: sidebar
        anchors.left: activity.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Theme.sidebarWidth
        color: Theme.sidebar

        PaneHeader {
            id: sideHeader
            width: parent.width
            title: "Artists"
        }

        Rectangle {
            id: searchBox
            anchors.top: sideHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            height: 30
            color: searchInput.activeFocus ? Theme.editor : Theme.chrome
            border.width: 1
            border.color: searchInput.activeFocus ? Theme.focus : Theme.separator

            Icon {
                id: searchIcon
                x: 8
                anchors.verticalCenter: parent.verticalCenter
                name: "search"
                size: 14
                color: Theme.textMuted
            }

            TextInput {
                id: searchInput
                objectName: "artistSearch"
                anchors.left: searchIcon.right
                anchors.right: parent.right
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.textPrimary
                selectionColor: Theme.primary
                selectedTextColor: Theme.textOnColor
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                selectByMouse: true
                clip: true
                onTextEdited: prototype.setSearch(text)
                Keys.onEscapePressed: { text = ""; prototype.setSearch(""); focus = false }
                Component.onCompleted: text = prototype.search

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: searchInput.text.length === 0
                    text: "Search artists"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }

        Text {
            id: countLine
            anchors.top: searchBox.bottom
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.topMargin: 10
            objectName: "artistCount"
            text: prototype.artists.length === prototype.totalCount
                ? prototype.totalCount + " artists"
                : prototype.artists.length + " of " + prototype.totalCount + " artists"
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeCaption
        }

        ListView {
            id: artistList
            objectName: "artistList"
            anchors.top: countLine.bottom
            anchors.topMargin: 6
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: prototype.artists
            ScrollBar.vertical: ThinScrollBar {}

            delegate: Rectangle {
                id: artistRow

                required property var modelData
                readonly property bool current: modelData.key === prototype.artistKey

                objectName: "artistRow_" + modelData.key
                width: ListView.view.width
                height: 32
                color: current ? Theme.selection : hit.containsMouse ? Theme.surface : "transparent"

                Rectangle {
                    visible: artistRow.current
                    width: 2
                    height: parent.height
                    color: Theme.primary
                }

                Text {
                    x: 16
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 64
                    text: artistRow.modelData.name
                    elide: Text.ElideRight
                    color: artistRow.current ? Theme.textPrimary : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: artistRow.modelData.trackCount
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                MouseArea {
                    id: hit
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: prototype.selectArtist(artistRow.modelData.key)
                }
            }
        }

        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: Theme.separator
            opacity: 0.6
        }
    }

    // ------------------------------------------------------------ editor area

    Rectangle {
        id: editor
        anchors.left: sidebar.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        color: Theme.chrome

        // Editor tab, as the tab strip of the application.
        Rectangle {
            id: tabStrip
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: Theme.tabHeight
            color: Theme.chrome

            Rectangle {
                height: parent.height
                width: Math.min(260, tabLabel.implicitWidth + 40)
                color: Theme.editor
                Rectangle { width: parent.width; height: 2; color: Theme.primary }
                Text {
                    id: tabLabel
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    text: prototype.artistName.length > 0 ? prototype.artistName : "Artists"
                    elide: Text.ElideRight
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }
        }

        Rectangle {
            id: pageArea
            anchors.top: tabStrip.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: statusBar.top
            color: Theme.editor

            // Nothing selected yet.
            Text {
                anchors.centerIn: parent
                visible: prototype.artistKey.length === 0
                text: "Choose an artist in the list."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Column {
                id: page
                objectName: "artistPage"
                visible: prototype.artistKey.length > 0
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 24
                anchors.leftMargin: 24
                anchors.rightMargin: 24
                spacing: 6

                Text {
                    text: "Artist"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    font.weight: Font.DemiBold
                }

                Text {
                    objectName: "artistNameTitle"
                    width: parent.width
                    text: prototype.artistName
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.weight: Theme.displayFontWeight
                    font.pixelSize: Theme.playlistTitleCompact
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }

                Text {
                    objectName: "artistMeta"
                    text: prototype.trackCount + (prototype.trackCount === 1 ? " track" : " tracks")
                        + (root.creditText.length > 0 ? "  ·  from " + root.creditText : "")
                    width: parent.width
                    elide: Text.ElideRight
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Item { width: 1; height: 14 }

                Row {
                    id: actionRow
                    spacing: 8

                    TextButton {
                        objectName: "playArtist"
                        kind: "primary"
                        icon: "play"
                        text: "Play"
                        tip: "Play every track of this artist"
                        onClicked: prototype.play()
                    }
                    TextButton {
                        objectName: "shuffleArtist"
                        kind: "neutral"
                        icon: "shuffle"
                        text: "Shuffle"
                        tip: "Play the tracks of this artist in random order"
                        onClicked: prototype.shuffle()
                    }
                    IconButton {
                        id: moreButton
                        visible: root.variant === "menu"
                        objectName: "artistMoreButton"
                        icon: "more"
                        iconSize: 18
                        width: 32
                        height: 32
                        tip: "More actions for this artist"
                        onClicked: root.openMenu()
                    }
                    TextButton {
                        visible: root.variant === "inline"
                        objectName: "thisIsOneArtistInline"
                        kind: "ghost"
                        text: "This is one artist"
                        enabledAction: prototype.canMakeOneArtist
                        onClicked: prototype.makeOneArtist()
                    }
                    TextButton {
                        visible: root.variant === "inline"
                        objectName: "splitArtistsInline"
                        kind: "ghost"
                        text: "Split into separate artists"
                        enabledAction: prototype.canSplit
                        onClicked: prototype.splitArtist()
                    }
                }

                Text {
                    objectName: "overrideHint"
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: prototype.canMakeOneArtist
                        ? "This is one artist keeps " + root.quoted(prototype.oneArtistCredits)
                            + " whole, on every track that has it."
                        : prototype.canSplit
                            ? "Split into separate artists cuts " + root.quoted(prototype.splitCredits)
                                + " at each “&” and “x”, on every track that has it."
                            : "No credit to change for this artist."
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            // Track list with the header of the application's track table.
            Item {
                id: trackTable
                objectName: "artistTracks"
                visible: prototype.artistKey.length > 0
                anchors.top: page.bottom
                anchors.topMargin: 18
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                readonly property int padding: 24
                readonly property int timeWidth: 64
                readonly property int albumWidth: Math.max(140, Math.round(width * 0.3))

                Row {
                    id: columnHeader
                    x: trackTable.padding
                    width: trackTable.width - 2 * trackTable.padding
                    height: 30

                    Text {
                        width: 48
                        height: parent.height
                        verticalAlignment: Text.AlignVCenter
                        text: "#"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }
                    Text {
                        width: parent.width - 48 - trackTable.albumWidth - trackTable.timeWidth
                        height: parent.height
                        verticalAlignment: Text.AlignVCenter
                        text: "Title"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }
                    Text {
                        width: trackTable.albumWidth
                        height: parent.height
                        verticalAlignment: Text.AlignVCenter
                        text: "Album"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }
                    Text {
                        width: trackTable.timeWidth
                        height: parent.height
                        horizontalAlignment: Text.AlignRight
                        verticalAlignment: Text.AlignVCenter
                        text: "Time"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }
                }

                Rectangle {
                    id: headerRule
                    x: trackTable.padding
                    anchors.top: columnHeader.bottom
                    width: columnHeader.width
                    height: 1
                    color: Theme.separator
                }

                ListView {
                    id: trackView
                    objectName: "artistTrackList"
                    anchors.top: headerRule.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: prototype.tracks
                    ScrollBar.vertical: ThinScrollBar {}

                    delegate: Rectangle {
                        id: trackRow

                        required property var modelData

                        objectName: "artistTrackRow"
                        width: ListView.view.width
                        height: Theme.rowHeight
                        color: rowHit.containsMouse ? Theme.surface : "transparent"

                        Row {
                            x: trackTable.padding
                            width: trackRow.width - 2 * trackTable.padding
                            height: parent.height

                            Text {
                                width: 48
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                text: trackRow.modelData.number
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                            }
                            Text {
                                width: parent.width - 48 - trackTable.albumWidth - trackTable.timeWidth
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                text: trackRow.modelData.title
                                elide: Text.ElideRight
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeBody
                            }
                            Text {
                                width: trackTable.albumWidth
                                height: parent.height
                                verticalAlignment: Text.AlignVCenter
                                text: trackRow.modelData.album
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                            }
                            Text {
                                width: trackTable.timeWidth
                                height: parent.height
                                horizontalAlignment: Text.AlignRight
                                verticalAlignment: Text.AlignVCenter
                                text: trackRow.modelData.time
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                            }
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: Theme.separator
                            opacity: 0.5
                        }

                        MouseArea {
                            id: rowHit
                            anchors.fill: parent
                            hoverEnabled: true
                        }
                    }
                }
            }
        }

        // Status line: the outcome of the last action, and the choices kept in this mock-up.
        Rectangle {
            id: statusBar
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 32
            color: Theme.chrome

            Text {
                objectName: "statusMessage"
                anchors.left: parent.left
                anchors.leftMargin: 24
                anchors.right: choiceText.left
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                text: prototype.message
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Row {
                id: choiceText
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12

                Text {
                    objectName: "choiceCount"
                    anchors.verticalCenter: parent.verticalCenter
                    text: prototype.choices.length + (prototype.choices.length === 1 ? " choice" : " choices")
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
                TextButton {
                    objectName: "resetChoices"
                    kind: "ghost"
                    text: "Reset choices"
                    implicitHeight: 24
                    onClicked: prototype.resetChoices()
                }
            }
        }
    }

    AppMenu {
        id: actionsMenu
        objectName: "artistActionsMenu"
        AppMenuItem {
            objectName: "thisIsOneArtist"
            text: "This is one artist"
            enabled: prototype.canMakeOneArtist
            onTriggered: prototype.makeOneArtist()
        }
        AppMenuItem {
            objectName: "splitArtists"
            text: "Split into separate artists"
            enabled: prototype.canSplit
            onTriggered: prototype.splitArtist()
        }
    }

    // A slim activity button, as in ActivityBar.qml.
    component ActivityIcon: Item {
        id: button

        property string icon: ""
        property string tip: ""
        property bool highlighted: false

        width: Theme.activityBarWidth
        height: Theme.activityBarWidth

        Rectangle {
            visible: button.highlighted
            width: 2
            height: parent.height
            color: Theme.primary
        }

        Icon {
            anchors.centerIn: parent
            name: button.icon
            size: 24
            color: button.highlighted || mouse.containsMouse ? Theme.textPrimary : Theme.textMuted
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
        }

        HoverTip {
            visible: mouse.containsMouse
            text: button.tip
        }
    }
}
