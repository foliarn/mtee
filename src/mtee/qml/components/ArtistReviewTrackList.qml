import QtQuick
import QtQuick.Controls.Basic
import Mtee

// Tracks of one identification step: file name, artists (clickable) and Edit. The
// header sorts by file name or by artist; there is no row selection, a lot is always
// the result of the current filter.
Item {
    id: list

    required property var listModel
    property int bottomInset: 0
    readonly property int padding: width < 600 ? 12 : 24
    readonly property int editWidth: 64
    readonly property real fileWidth: Math.max(160, (width - 2 * padding - editWidth) * 0.48)
    readonly property real artistWidth: Math.max(120, width - 2 * padding - editWidth - fileWidth)
    signal editRequested(string trackId)
    signal artistClicked(string name)

    Row {
        id: header
        x: list.padding
        width: list.width - 2 * list.padding
        height: 30

        HeaderCell {
            width: list.fileWidth
            label: "Filename"
            sortKey: "filename"
        }

        HeaderCell {
            width: list.artistWidth
            label: "Artists"
            sortKey: "artist"
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
        objectName: "artistReviewTracks"
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
            required property string trackId
            required property string filename
            required property string artists
            required property var credits
            required property string applyState
            required property string applyError
            required property string applyNote
            required property string note
            required property bool incomplete
            readonly property string subText: {
                if (applyState === "failed")
                    return "Not applied: " + applyError
                if (applyState === "queued" || applyState === "running")
                    return "Applying…"
                if (applyState === "cancelled")
                    return "Application cancelled. Retry to finish it."
                if (applyNote.length > 0)
                    return applyNote
                if (incomplete && credits.length === 0)
                    return "No artist yet: use Edit to add one."
                if (incomplete)
                    return "A title is missing: use Edit."
                return note
            }
            readonly property color subColor: applyState === "failed" ? Theme.danger
                : applyState === "queued" || applyState === "running" ? Theme.textSecondary
                : applyNote.length > 0 || incomplete ? Theme.warning : Theme.textMuted

            width: ListView.view.width
            height: subText.length > 0 ? 58 : 42
            color: rowHover.hovered ? Theme.surface : "transparent"

            HoverHandler { id: rowHover }

            Column {
                x: list.padding
                anchors.verticalCenter: parent.verticalCenter
                width: list.fileWidth - 12
                spacing: 2

                Text {
                    width: parent.width
                    text: row.filename
                    elide: Text.ElideMiddle
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text {
                    visible: row.subText.length > 0
                    width: parent.width
                    text: row.subText
                    elide: Text.ElideRight
                    color: row.subColor
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            Flow {
                id: names
                x: list.padding + list.fileWidth
                anchors.verticalCenter: parent.verticalCenter
                width: list.artistWidth - 12
                height: 20
                clip: true
                spacing: 0

                Repeater {
                    model: row.credits

                    delegate: Text {
                        id: credit
                        required property int index
                        required property var modelData
                        text: modelData.name + (index < row.credits.length - 1 ? ", " : "")
                        color: creditMouse.containsMouse ? Theme.primary : Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                        font.underline: creditMouse.containsMouse

                        MouseArea {
                            id: creditMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: list.artistClicked(credit.modelData.name)
                        }
                    }
                }

                Text {
                    visible: row.credits.length === 0
                    text: "—"
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }

            HoverHandler {
                id: namesHover
                parent: names
            }

            HoverTip {
                parent: names
                visible: namesHover.hovered && row.artists.length > 0
                text: row.artists
            }

            TextButton {
                objectName: "editTrack_" + row.index
                anchors.right: parent.right
                anchors.rightMargin: list.padding
                anchors.verticalCenter: parent.verticalCenter
                implicitHeight: 26
                text: "Edit"
                kind: "ghost"
                onClicked: list.editRequested(row.trackId)
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
