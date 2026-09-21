import QtQuick
import QtQuick.Window
import Mtee
import "views"

Window {
    id: root

    objectName: "mteeWindow"
    property var demoWorkspace: workspace
    readonly property string currentScreen: workspace.screen

    width: 1440
    height: 900
    minimumWidth: 880
    minimumHeight: 600
    visible: true
    title: "MTEE · " + workspace.scenarioName
    color: Theme.background

    Item {
        id: chrome
        anchors.fill: parent
        anchors.margins: Theme.spacing

        Item {
            id: topBar
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 46

            Row {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacing

                Text {
                    text: "MTEE"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: 19
                    font.letterSpacing: 1.8
                }

                Rectangle {
                    width: 1
                    height: 20
                    color: Theme.border
                }

                Text {
                    text: "Demo workspace"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            Row {
                anchors.centerIn: parent
                spacing: Theme.spacingSmall

                ToolButton {
                    text: "Browser"
                    primary: root.currentScreen === "browser"
                    onClicked: workspace.setScreen("browser")
                }
                ToolButton {
                    text: "Listening"
                    primary: root.currentScreen === "listening"
                    onClicked: workspace.setScreen("listening")
                }
                ToolButton {
                    text: "Convert"
                    primary: root.currentScreen === "convert"
                    onClicked: workspace.setScreen("convert")
                }
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacingSmall

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: workspace.scenarioName
                    color: Theme.accent
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                ToolButton {
                    text: "Run sample task"
                    onClicked: shell.startSampleJob()
                }
            }
        }

        Loader {
            id: viewLoader
            anchors.top: topBar.bottom
            anchors.topMargin: Theme.spacing
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: bottomArea.top
            anchors.bottomMargin: Theme.spacing
            sourceComponent: root.currentScreen === "listening" ? listeningComponent
                : root.currentScreen === "convert" ? convertComponent
                : browserComponent
        }

        Component {
            id: browserComponent
            BrowserView { workspace: root.demoWorkspace }
        }

        Component {
            id: listeningComponent
            ListeningView { workspace: root.demoWorkspace }
        }

        Component {
            id: convertComponent
            ConvertView { workspace: root.demoWorkspace }
        }

        Item {
            id: bottomArea
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.currentScreen === "listening" ? 0 : 142
            visible: height > 0

            Panel {
                id: taskPanel
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 62

                SectionLabel {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: Theme.spacing
                    text: "Session tasks"
                }

                JobStrip {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.leftMargin: 130
                    anchors.rightMargin: Theme.spacing
                    anchors.topMargin: Theme.spacingSmall
                    anchors.bottomMargin: Theme.spacingSmall
                    model: jobsModel
                    onCancelRequested: (jobId) => shell.cancelJob(jobId)
                }
            }

            PlayerBar {
                id: player
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 72
                trackTitle: "Carrier Wave"
                trackArtist: "Loop Foundry"
                onListeningViewRequested: workspace.setScreen("listening")
            }
        }
    }
}
