import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import Mtee

// Profile tab, opened from the activity bar (plans 114-115): the display name, the picture
// and the listening statistics of the chosen period. Every figure comes from the real
// models; the picture is copied and shown as it is, never cropped.
Flickable {
    id: profileFlick

    objectName: "profilePage"
    required property var workspace
    property int bottomInset: 0
    readonly property bool available: typeof profile !== "undefined" && typeof statistics !== "undefined"
    readonly property real pageWidth: Math.min(880, profileFlick.width - 64)
    readonly property var periods: [
        { "key": "week", "label": "This week" },
        { "key": "month", "label": "This month" },
        { "key": "year", "label": "This year" },
        { "key": "all", "label": "All time" }
    ]
    property string notice: ""

    contentHeight: profileContent.implicitHeight + 64 + bottomInset
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ThinScrollBar {}

    // Read again every time the page opens; later listenings and resets refresh it too.
    Component.onCompleted: if (profileFlick.available) statistics.refresh()

    Connections {
        target: profileFlick.available ? profile : null
        ignoreUnknownSignals: true
        function onNoticeRaised(message) { profileFlick.notice = message }
    }

    FileDialog {
        id: pictureDialog
        title: "Choose a profile picture"
        nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"]
        onAccepted: profile.setAvatarFrom(String(selectedFile))
    }

    Column {
        id: profileContent
        x: 32
        y: 28
        width: profileFlick.pageWidth
        spacing: 24

        Text {
            visible: !profileFlick.available
            width: parent.width
            wrapMode: Text.WordWrap
            text: "The profile is not available in the demo."
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSecondary
        }

        Row {
            visible: profileFlick.available
            spacing: 24
            width: parent.width

            Rectangle {
                id: avatarFrame
                width: 112
                height: 112
                color: Theme.surface
                clip: true

                Image {
                    objectName: "profileAvatar"
                    anchors.fill: parent
                    source: profileFlick.available ? profile.avatarSource : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: source.toString().length > 0
                }

                Icon {
                    anchors.centerIn: parent
                    visible: !profileFlick.available || profile.avatarSource.length === 0
                    name: "profile"
                    size: 48
                    color: Theme.textMuted
                }
            }

            Column {
                width: parent.width - avatarFrame.width - 24
                spacing: 10

                Text {
                    objectName: "profileName"
                    width: parent.width
                    text: profileFlick.available && profile.displayName.length > 0 ? profile.displayName : "MTEE"
                    elide: Text.ElideRight
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: 30
                    font.weight: Theme.displayFontWeight
                }

                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: "Shown as the creator of your playlists. Stored on this computer only. Leave the name empty to show MTEE."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Row {
                    spacing: 8

                    TextButton {
                        objectName: "chooseAvatar"
                        text: "Change picture…"
                        kind: "ghost"
                        enabledAction: profileFlick.available && !profile.busy
                        onClicked: pictureDialog.open()
                    }

                    TextButton {
                        objectName: "removeAvatar"
                        text: "Remove picture"
                        kind: "ghost"
                        enabledAction: profileFlick.available && profile.hasAvatar && !profile.busy
                        onClicked: profile.clearAvatar()
                    }
                }
            }
        }

        Row {
            visible: profileFlick.available
            spacing: 8
            width: parent.width

            TextField {
                id: nameField
                objectName: "displayNameInput"
                width: Math.min(340, parent.width - 120)
                height: 36
                text: profileFlick.available ? profile.displayName : ""
                maximumLength: 240
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                background: Rectangle {
                    color: Theme.surface
                    border.color: nameField.activeFocus ? Theme.focus : Theme.separator
                }
                onAccepted: profile.setDisplayName(text)
            }

            TextButton {
                objectName: "saveDisplayName"
                implicitHeight: 36
                text: "Save name"
                kind: "primary"
                onClicked: profile.setDisplayName(nameField.text)
            }
        }

        Text {
            visible: profileFlick.notice.length > 0
            width: parent.width
            wrapMode: Text.WordWrap
            text: profileFlick.notice
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Rectangle { visible: profileFlick.available; width: parent.width; height: 1; color: Theme.separator }

        Row {
            visible: profileFlick.available
            width: parent.width
            spacing: 16

            Item {
                width: parent.width - periodRow.width - 16
                height: periodRow.height

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Listening"
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: Theme.fontSizeTitle
                    font.weight: Font.Bold
                }
            }

            Row {
                id: periodRow
                objectName: "periodSelector"
                spacing: 4

                Repeater {
                    model: profileFlick.periods

                    delegate: TextButton {
                        required property var modelData
                        objectName: "period_" + modelData.key
                        implicitHeight: 28
                        text: modelData.label
                        kind: profileFlick.available && statistics.period === modelData.key ? "primary" : "ghost"
                        onClicked: statistics.setPeriod(modelData.key)
                    }
                }
            }
        }

        Row {
            visible: profileFlick.available
            width: parent.width
            spacing: 12

            Kpi {
                objectName: "kpiListening"
                label: "Listening time"
                value: profileFlick.available ? profileFlick.formatDuration(statistics.listeningMs) : ""
                width: (parent.width - 12) / 2
            }

            Kpi {
                objectName: "kpiPlays"
                label: "Plays"
                value: profileFlick.available ? String(statistics.countedPlays) : ""
                width: (parent.width - 12) / 2
            }
        }

        Text {
            visible: profileFlick.available && statistics.error.length > 0
            width: parent.width
            wrapMode: Text.WordWrap
            text: profileFlick.available ? "The statistics could not be read: " + statistics.error : ""
            color: Theme.danger
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        // Listening over time: one bar per day, or per month for the whole history.
        Column {
            visible: profileFlick.available
            width: parent.width
            spacing: 8

            Text {
                text: profileFlick.available ? "Listening over time · " + statistics.periodLabel : ""
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                font.weight: Font.DemiBold
            }

            Item {
                id: chart
                objectName: "listeningChart"
                width: parent.width
                height: 176

                readonly property var bars: profileFlick.available ? Array.from(statistics.series) : []
                readonly property real peak: {
                    let top = 1
                    for (let i = 0; i < bars.length; i++)
                        top = Math.max(top, bars[i].listeningMs)
                    return top
                }
                readonly property int labelStep: bars.length > 12 ? Math.ceil(bars.length / 6) : 1
                readonly property real barSpacing: 3
                readonly property real barWidth: bars.length > 0
                    ? (width - barSpacing * (bars.length - 1)) / bars.length : 0

                Rectangle {
                    width: parent.width
                    height: 1
                    y: 120
                    color: Theme.separator
                }

                Row {
                    id: barRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 120
                    spacing: chart.barSpacing

                    Repeater {
                        model: chart.bars

                        delegate: Item {
                            id: barItem
                            required property var modelData
                            required property int index
                            width: chart.barWidth
                            height: barRow.height

                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: barItem.modelData.listeningMs > 0
                                    ? Math.max(2, barItem.modelData.listeningMs / chart.peak * barRow.height) : 0
                                color: barMouse.containsMouse ? Theme.primaryHover : Theme.primary
                            }

                            MouseArea {
                                id: barMouse
                                anchors.fill: parent
                                hoverEnabled: true
                            }

                            HoverTip {
                                visible: barMouse.containsMouse
                                text: profileFlick.bucketLabel(barItem.modelData) + " · "
                                    + profileFlick.formatDuration(barItem.modelData.listeningMs)
                            }
                        }
                    }
                }

                // Labels sit at the position of their bar; only every labelStep-th bar has one.
                Item {
                    anchors.top: barRow.bottom
                    anchors.topMargin: 8
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 16

                    Repeater {
                        model: chart.bars

                        delegate: Text {
                            required property var modelData
                            required property int index
                            x: index * (chart.barWidth + chart.barSpacing)
                            width: chart.barWidth * chart.labelStep
                            visible: index % chart.labelStep === 0
                            text: profileFlick.bucketLabel(modelData)
                            elide: Text.ElideNone
                            color: Theme.textMuted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeCaption
                        }
                    }
                }
            }
        }

        Row {
            visible: profileFlick.available
            width: parent.width
            spacing: 24

            RankingList {
                objectName: "topTracks"
                width: (parent.width - 48) / 3
                heading: "Top tracks"
                rows: profileFlick.available ? Array.from(statistics.topTracks) : []
                emptyText: "No plays in this period."
                primaryKey: "title"
                secondaryKey: "artist"
            }

            RankingList {
                objectName: "topArtists"
                width: (parent.width - 48) / 3
                heading: "Top artists"
                rows: profileFlick.available ? Array.from(statistics.topArtists) : []
                emptyText: "Artist ranking is not available yet."
                primaryKey: "name"
                secondaryKey: ""
            }

            RankingList {
                objectName: "topAlbums"
                width: (parent.width - 48) / 3
                heading: "Top albums"
                rows: profileFlick.available ? Array.from(statistics.topAlbums) : []
                emptyText: "No plays in this period."
                primaryKey: "album"
                secondaryKey: ""
            }
        }

        Text {
            visible: profileFlick.available
            width: parent.width
            bottomPadding: 24
            wrapMode: Text.WordWrap
            text: "Plays count a track once 30 seconds were heard, or once a track shorter than 30 seconds is played to its end. Periods use the local calendar; weeks start on Monday."
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    function formatDuration(milliseconds) {
        const minutes = Math.round(milliseconds / 60000)
        const hours = Math.floor(minutes / 60)
        const rest = minutes % 60
        return hours > 0 ? hours + " h " + rest + " min" : rest + " min"
    }

    // A bar's label: the day ("Mon 13") or, for the whole history, the month ("Oct 26").
    function bucketLabel(bucket) {
        const date = new Date(bucket.start)
        return bucket.granularity === "month" ? Qt.formatDate(date, "MMM yy") : Qt.formatDate(date, "ddd d")
    }

    component Kpi: Rectangle {
        id: kpi
        property string label: ""
        property string value: ""

        height: 84
        color: Theme.surface

        Column {
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6

            Text {
                text: kpi.label
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                text: kpi.value
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: 24
                font.weight: Theme.displayFontWeight
                font.features: { "tnum": 1 }
            }
        }
    }

    component RankingList: Column {
        id: ranking
        property string heading: ""
        property var rows: []
        property string emptyText: ""
        property string primaryKey: ""
        property string secondaryKey: ""

        spacing: 8

        Text {
            text: ranking.heading
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.weight: Font.DemiBold
        }

        Rectangle { width: parent.width; height: 1; color: Theme.separator }

        Repeater {
            model: Array.from(ranking.rows).slice(0, 5)

            delegate: Item {
                id: rankItem
                required property var modelData
                required property int index
                width: ranking.width
                height: 40

                Text {
                    id: rankNumber
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    text: String(rankItem.index + 1)
                    color: Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    font.features: { "tnum": 1 }
                }

                Column {
                    anchors.left: rankNumber.right
                    anchors.right: plays.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        width: parent.width
                        text: rankItem.modelData[ranking.primaryKey] || ""
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    Text {
                        visible: ranking.secondaryKey.length > 0
                        width: parent.width
                        text: ranking.secondaryKey.length > 0 ? rankItem.modelData[ranking.secondaryKey] || "" : ""
                        elide: Text.ElideRight
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }

                Text {
                    id: plays
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(rankItem.modelData.countedPlays)
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                    font.features: { "tnum": 1 }
                }
            }
        }

        Text {
            visible: ranking.rows.length === 0
            width: parent.width
            wrapMode: Text.WordWrap
            topPadding: 6
            text: ranking.emptyText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
