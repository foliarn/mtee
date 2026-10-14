import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Sidebar of the Artists activity: the artists of the core index, with a search on their
// names and the number of tracks of each. A click opens the artist page as an editor tab.
Item {
    id: pane

    required property var workspace
    readonly property var artists: pane.workspace.artistList
    readonly property string activeKey: {
        const groups = pane.workspace.groups
        if (groups.length === 0)
            return ""
        const active = groups[pane.workspace.activeGroup].active
        return active.indexOf("artist:") === 0 ? active.slice("artist:".length) : ""
    }

    function artistsText(count) {
        return count === 1 ? "1 artist" : count + " artists"
    }

    objectName: "artistsPane"

    PaneHeader {
        id: header
        width: parent.width
        title: "Artists"
    }

    Rectangle {
        id: searchBox
        anchors.top: header.bottom
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
            onTextEdited: pane.artists.setFilterText(text)
            Keys.onEscapePressed: { text = ""; pane.artists.setFilterText(""); focus = false }
            Component.onCompleted: text = pane.artists.filterText

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
        objectName: "artistCount"
        anchors.top: searchBox.bottom
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.topMargin: 10
        text: pane.artists.count === pane.artists.totalCount
            ? pane.artistsText(pane.artists.totalCount)
            : pane.artists.count + " of " + pane.artistsText(pane.artists.totalCount)
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeCaption
    }

    Text {
        objectName: "artistsEmpty"
        anchors.top: countLine.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        anchors.topMargin: 12
        visible: pane.artists.totalCount === 0
        wrapMode: Text.WordWrap
        text: "No artists yet. Artists come from the Artist tag of your files."
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
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
        model: pane.artists
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: artistRow

            required property var modelData
            readonly property bool current: modelData.key === pane.activeKey

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
                onClicked: pane.workspace.openArtistPage(artistRow.modelData.key, artistRow.modelData.name)
            }
        }
    }
}
