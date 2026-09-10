import QtQuick
import QtQuick.Window
import Mtee

// Window of the foundation step. It draws the named zones of PLAN.md section 3
// with invented data: explorer, tabs, two panes, folded inspector, common
// player and background tasks. No user file is read here.
Window {
    id: root

    readonly property bool compact: width < Theme.compactWidth
    property bool listening: false
    property int activeTab: 0
    readonly property var tabs: ["Downloads", "Collection", "Convert"]

    width: 1440
    height: 900
    minimumWidth: 880
    minimumHeight: 560
    visible: true
    title: "MTEE"
    color: Theme.background

    // Top bar: application name, mode of the run and startup state.
    Item {
        id: topBar
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.spacing
        height: 34

        Text {
            id: appName
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "MTEE"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.letterSpacing: 1.5
        }

        Text {
            anchors.left: appName.right
            anchors.leftMargin: Theme.spacing
            anchors.verticalCenter: parent.verticalCenter
            text: shell.modeLabel + " · v" + shell.applicationVersion
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Text {
            id: statusText
            objectName: "statusText"
            anchors.right: detailsToggle.left
            anchors.rightMargin: Theme.spacing
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(0, parent.width / 3)
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideMiddle
            text: shell.statusMessage
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        ToolButton {
            id: detailsToggle
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: shell.detailsVisible ? "Hide details" : "Details"
            onClicked: shell.setDetailsVisible(!shell.detailsVisible)
        }
    }

    ExplorerPanel {
        id: explorer
        anchors.top: topBar.bottom
        anchors.topMargin: Theme.spacing
        anchors.left: parent.left
        anchors.leftMargin: Theme.spacing
        anchors.bottom: player.top
        anchors.bottomMargin: Theme.spacing
        width: Theme.sidebarWidth
        visible: !root.compact
        roots: [
            { "name": "Music", "depth": 0 },
            { "name": "Downloads", "depth": 1 },
            { "name": "Collection", "depth": 1 },
            { "name": "Sets 2026", "depth": 2 },
            { "name": "Samples", "depth": 1 }
        ]
    }

    // Central area: tabs, breadcrumbs, panes and background tasks.
    Item {
        id: central
        anchors.top: topBar.bottom
        anchors.topMargin: Theme.spacing
        anchors.left: root.compact ? parent.left : explorer.right
        anchors.leftMargin: Theme.spacing
        anchors.right: shell.detailsVisible && !root.compact ? details.left : parent.right
        anchors.rightMargin: Theme.spacing
        anchors.bottom: player.top
        anchors.bottomMargin: Theme.spacing

        Row {
            id: tabRow
            anchors.top: parent.top
            anchors.left: parent.left
            height: 30
            spacing: Theme.spacingSmall
            visible: !root.listening

            Repeater {
                model: root.tabs
                delegate: ToolButton {
                    required property int index
                    required property string modelData
                    text: modelData
                    primary: root.activeTab === index
                    onClicked: root.activeTab = index
                }
            }
        }

        Panel {
            id: browser
            anchors.top: tabRow.bottom
            anchors.topMargin: Theme.spacing
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: jobs.top
            anchors.bottomMargin: Theme.spacing
            visible: !root.listening

            Item {
                id: toolbar
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: Theme.spacing
                height: 26

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Music / " + root.tabs[root.activeTab]
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.spacingSmall

                    ToolButton { text: "Search…"; enabledAction: false }
                    ToolButton { text: "Table"; primary: true; enabledAction: false }
                    ToolButton { text: "Artwork"; enabledAction: false }
                }
            }

            TrackTable {
                id: firstPane
                anchors.top: toolbar.bottom
                anchors.topMargin: Theme.spacingSmall
                anchors.left: parent.left
                anchors.leftMargin: Theme.spacing
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Theme.spacing
                width: root.compact
                    ? parent.width - 2 * Theme.spacing
                    : (parent.width - 3 * Theme.spacing) / 2
                model: tracksModel
            }

            Rectangle {
                id: paneSplit
                anchors.left: firstPane.right
                anchors.leftMargin: Theme.spacing / 2
                anchors.top: firstPane.top
                anchors.bottom: firstPane.bottom
                width: 1
                color: Theme.border
                visible: !root.compact
            }

            TrackTable {
                id: secondPane
                anchors.left: paneSplit.right
                anchors.leftMargin: Theme.spacing / 2
                anchors.right: parent.right
                anchors.rightMargin: Theme.spacing
                anchors.top: firstPane.top
                anchors.bottom: firstPane.bottom
                visible: !root.compact
                currentRow: 3
                playingRow: -1
                model: tracksModel
            }
        }

        // Listening view: the central space shows the played track. The common
        // player is hidden in this mode to avoid duplicated commands.
        Panel {
            id: listeningView
            anchors.fill: parent
            visible: root.listening

            Rectangle {
                id: bigArtwork
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.spacingLarge
                width: 260
                height: 260
                radius: Theme.panelRadius
                color: Theme.activeSurface

                Text {
                    anchors.centerIn: parent
                    text: "No artwork"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            Column {
                anchors.top: bigArtwork.top
                anchors.left: bigArtwork.right
                anchors.leftMargin: Theme.spacingLarge
                anchors.right: parent.right
                anchors.rightMargin: Theme.spacingLarge
                spacing: Theme.spacingSmall

                Text {
                    text: "Carrier Wave"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 28
                }

                Text {
                    text: "Loop Foundry · Techno · 134 BPM · 5A"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    text: "Editable metadata and analysis tags take place here."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            // Classic progress bar until the waveform step replaces it.
            Rectangle {
                id: listeningProgress
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: listeningTransport.top
                anchors.margins: Theme.spacingLarge
                anchors.bottomMargin: Theme.spacing
                height: 6
                radius: 3
                color: Theme.activeSurface

                Rectangle {
                    width: parent.width * 0.32
                    height: parent.height
                    radius: parent.radius
                    color: Theme.accent
                }
            }

            Item {
                id: listeningTransport
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: Theme.spacingLarge
                height: 32

                Text {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: "2:18 / 7:12"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Row {
                    anchors.centerIn: parent
                    spacing: Theme.spacingSmall

                    ToolButton { text: "Previous"; enabledAction: false }
                    ToolButton { text: "Play"; primary: true; enabledAction: false }
                    ToolButton { text: "Next"; enabledAction: false }
                }

                ToolButton {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Back to browser"
                    onClicked: root.listening = false
                }
            }
        }

        Panel {
            id: jobs
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 128
            visible: !root.listening

            SectionLabel {
                id: jobsHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.spacing
                text: "Background tasks"
            }

            ToolButton {
                id: sampleJobButton
                objectName: "sampleJobButton"
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.spacingSmall
                text: "Run sample task"
                onClicked: shell.startSampleJob()
            }

            JobStrip {
                anchors.top: jobsHeader.bottom
                anchors.topMargin: Theme.spacingSmall
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: Theme.spacing
                model: jobsModel
                onCancelRequested: (jobId) => shell.cancelJob(jobId)
            }
        }
    }

    DetailsPanel {
        id: details
        anchors.top: central.top
        anchors.right: parent.right
        anchors.rightMargin: Theme.spacing
        anchors.bottom: player.top
        anchors.bottomMargin: Theme.spacing
        width: Theme.detailsWidth
        visible: shell.detailsVisible && !root.compact
        trackTitle: "Carrier Wave"
        trackArtist: "Loop Foundry"
        trackGenre: "Techno"
        trackBpm: "134"
        trackKey: "5A"
        onCloseRequested: shell.setDetailsVisible(false)
    }

    PlayerBar {
        id: player
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacing
        height: root.listening ? 0 : Theme.playerHeight
        visible: !root.listening
        trackTitle: "Carrier Wave"
        trackArtist: "Loop Foundry"
        onListeningViewRequested: root.listening = true
    }
}
