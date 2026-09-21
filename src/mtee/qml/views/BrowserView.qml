import QtQuick
import Mtee
import "../components"

Panel {
    id: browser

    objectName: "browserView"
    property var workspace
    property bool compact: width < 1160
    property bool narrow: width < 930
    property string activePane: "library"
    property bool showOptionalColumns: false
    property string folderLabel: "Collection"

    function togglePane() {
        activePane = activePane === "library" ? "inspector" : "library"
    }

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacing
        spacing: Theme.spacing

        Item {
            width: parent.width
            height: 30

            Text {
                id: titleLabel
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: "Music  /  " + browser.folderLabel
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
            }

            Text {
                anchors.left: titleLabel.right
                anchors.leftMargin: Theme.spacing
                anchors.verticalCenter: parent.verticalCenter
                text: workspace.selectedRows.length + " selected"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Row {
                id: controls
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacingSmall

                ToolButton {
                    text: "Table"
                    primary: !workspace.artworkView
                    onClicked: workspace.setArtworkView(false)
                }
                ToolButton {
                    text: "Artwork"
                    primary: workspace.artworkView
                    onClicked: workspace.setArtworkView(true)
                }
                ToolButton {
                    text: showOptionalColumns ? "Fewer columns" : "More columns"
                    visible: !workspace.artworkView
                    onClicked: showOptionalColumns = !showOptionalColumns
                }
                ToolButton {
                    text: workspace.inspectorVisible ? "Hide inspector" : "Inspector"
                    onClicked: workspace.setInspectorVisible(!workspace.inspectorVisible)
                }
            }

        }

        TabGroup {
            id: tabs
            width: parent.width
            labels: ["Collection", "Downloads", "Sets 2026"]
            currentIndex: 0
            onSelected: (index) => folderLabel = labels[index]
        }

        Row {
            width: parent.width
            height: parent.height - 30 - tabs.height - Theme.spacing * 2
            spacing: Theme.spacing

            ExplorerPane {
                id: explorer
                width: 216
                height: parent.height
                visible: !browser.compact && (!browser.narrow || browser.activePane === "library")
                roots: [
                    { "name": "Music", "depth": 0 },
                    { "name": "Collection", "depth": 1 },
                    { "name": "Sets 2026", "depth": 2 },
                    { "name": "Downloads", "depth": 1 },
                    { "name": "Samples", "depth": 1 },
                    { "name": "Échantillons", "depth": 2 }
                ]
                onFolderSelected: (folder) => folderLabel = folder
            }

            Panel {
                id: library
                width: browser.narrow ? parent.width : (
                    browser.compact ? parent.width : (
                        workspace.inspectorVisible
                            ? parent.width - explorer.width - inspector.width - Theme.spacing * 2
                            : parent.width - explorer.width - Theme.spacing
                    ))
                height: parent.height
                visible: !browser.narrow || browser.activePane === "library"

                Column {
                    anchors.fill: parent
                    anchors.margins: Theme.spacing
                    spacing: Theme.spacingSmall

                    Row {
                        width: parent.width
                        height: 28
                        spacing: Theme.spacingSmall

                        Rectangle {
                            width: Math.max(120, parent.width * 0.46)
                            height: 28
                            radius: Theme.controlRadius
                            color: Theme.background
                            border.width: 1
                            border.color: Theme.border

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: Theme.spacingSmall
                                anchors.verticalCenter: parent.verticalCenter
                                text: "Search collection"
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }

                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: workspace.multiSelection ? "Mixed values are shown in the inspector" : "Double-click a row to play"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }

                        Item { width: Math.max(0, parent.width - implicitHint.width - 145); height: 1 }

                        Text {
                            id: implicitHint
                            anchors.verticalCenter: parent.verticalCenter
                            text: browser.narrow ? "Library" : "6 tracks"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }

                    Row {
                        visible: browser.narrow
                        width: parent.width
                        height: 30
                        spacing: Theme.spacingSmall

                        ToolButton {
                            text: "Library"
                            primary: browser.activePane === "library"
                            onClicked: browser.activePane = "library"
                        }
                        ToolButton {
                            text: "Inspector"
                            primary: browser.activePane === "inspector"
                            onClicked: browser.activePane = "inspector"
                        }
                    }

                    TrackTable {
                        id: table
                        width: parent.width
                        height: parent.height - 74
                        workspace: browser.workspace
                        showOptional: browser.showOptionalColumns
                    }

                    ArtworkGrid {
                        visible: workspace.artworkView
                        width: parent.width
                        height: parent.height - 74
                        workspace: browser.workspace
                        cardWidth: Math.max(150, Math.min(210, width / 4 - Theme.spacing))
                    }
                }
            }

            MetadataInspector {
                id: inspector
                property bool compactMode: browser.narrow
                workspace: browser.workspace
                width: browser.narrow ? parent.width : 294
                height: parent.height
                visible: workspace.inspectorVisible && (!browser.narrow || browser.activePane === "inspector")
                onCloseRequested: workspace.setInspectorVisible(false)
            }
        }
    }
}
