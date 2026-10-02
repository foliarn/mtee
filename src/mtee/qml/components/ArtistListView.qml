import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Artists of one identification step: name, number of tracks and an Edit menu with
// Rename, Merge into… and Delete artist.
Item {
    id: list

    required property var listModel
    property int bottomInset: 0
    readonly property int padding: width < 600 ? 12 : 24
    readonly property int editWidth: 64
    readonly property int countWidth: 110
    signal artistClicked(string name)
    signal actionRequested(string action, string artistId, string name)

    Row {
        id: header
        x: list.padding
        width: list.width - 2 * list.padding
        height: 30

        HeaderCell {
            width: parent.width - list.countWidth - list.editWidth
            label: "Artist"
            sortKey: "artist"
        }

        HeaderCell {
            width: list.countWidth
            label: "Tracks"
            sortKey: "tracks"
        }
    }

    Rectangle {
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.separator
    }

    ListView {
        id: view
        objectName: "artistReviewArtists"
        anchors.top: header.bottom
        anchors.topMargin: 1
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.bottomMargin: list.bottomInset
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: list.listModel
        ScrollBar.vertical: ThinScrollBar {}

        delegate: Rectangle {
            id: row

            required property int index
            required property string artistId
            required property string name
            required property int tracks

            width: ListView.view.width
            height: 42
            color: rowHover.hovered ? Theme.surface : "transparent"

            HoverHandler { id: rowHover }

            Text {
                id: label
                x: list.padding
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 2 * list.padding - list.countWidth - list.editWidth - 12
                text: row.name
                elide: Text.ElideRight
                color: nameMouse.containsMouse ? Theme.primary : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                font.underline: nameMouse.containsMouse

                MouseArea {
                    id: nameMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: list.artistClicked(row.name)
                }
            }

            Text {
                x: list.padding + (parent.width - 2 * list.padding - list.countWidth - list.editWidth)
                anchors.verticalCenter: parent.verticalCenter
                text: row.tracks
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                id: editButton
                objectName: "editArtist_" + row.index
                anchors.right: parent.right
                anchors.rightMargin: list.padding
                anchors.verticalCenter: parent.verticalCenter
                implicitHeight: 26
                text: "Edit"
                kind: "ghost"
                onClicked: menu.popup(editButton, 0, editButton.height)
            }

            AppMenu {
                id: menu
                implicitWidth: 180
                AppMenuItem { text: "Rename"; onTriggered: list.actionRequested("rename", row.artistId, row.name) }
                AppMenuItem { text: "Merge into…"; onTriggered: list.actionRequested("merge", row.artistId, row.name) }
                AppMenuSeparator {}
                AppMenuItem { text: "Delete artist"; onTriggered: list.actionRequested("delete", row.artistId, row.name) }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.separator
                opacity: 0.5
            }
        }
    }

    component HeaderCell: Item {
        id: cell

        property string label: ""
        property string sortKey: ""
        readonly property bool sorted: list.listModel.sortKey === sortKey

        height: 30

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            Text {
                text: cell.label
                color: cell.sorted ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.DemiBold
            }

            Icon {
                visible: cell.sorted
                anchors.verticalCenter: parent.verticalCenter
                name: list.listModel.sortAscending ? "arrow-up" : "arrow-down"
                size: 12
                color: Theme.primary
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: list.listModel.toggleSort(cell.sortKey)
        }
    }
}
