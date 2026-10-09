import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../components"

Rectangle {
    id: page
    required property var manager
    readonly property var state: manager ? manager.state : ({})
    readonly property int marginSize: width < 700 ? 18 : 32
    property bool requested: false

    objectName: "genreUncertainPage"
    color: Theme.editor

    function requestRows() {
        if (!requested && !state.busy) {
            requested = true
            manager.openUncertain()
        }
    }
    Component.onCompleted: requestRows()
    Connections {
        target: manager
        function onChanged() { page.requestRows() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: page.marginSize
            Layout.rightMargin: page.marginSize
            Layout.topMargin: 27
            Layout.bottomMargin: 22
            spacing: 9
            SectionLabel { text: "GENRE MANAGER" }
            Text {
                text: "Uncertain"
                color: Theme.textPrimary
                font.family: Theme.displayFontFamily
                font.pixelSize: Theme.fontSizeHeading
                font.weight: Font.Bold
            }
            Text {
                Layout.fillWidth: true
                text: "Artist genre contributions that need a decision. Choose from confirmed "
                    + "credits, or leave them unresolved. Track classification is unaffected."
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
                wrapMode: Text.WordWrap
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ColumnLayout {
                width: parent.width
                spacing: 0
                Text {
                    visible: !page.state.busy && !(page.state.uncertainties || []).length
                    Layout.leftMargin: page.marginSize
                    Layout.topMargin: 24
                    text: "No artist contributions need a decision."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
                Repeater {
                    model: page.state.uncertainties || []
                    delegate: Rectangle {
                        id: uncertainty
                        required property var modelData
                        property var selectedIds: []
                        Layout.fillWidth: true
                        implicitHeight: details.implicitHeight + 33
                        color: "transparent"

                        ColumnLayout {
                            id: details
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: page.marginSize
                            anchors.rightMargin: page.marginSize
                            anchors.topMargin: 16
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: uncertainty.modelData.title || "Untitled track"
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSecondary
                                    font.weight: Font.DemiBold
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: (uncertainty.modelData.genres || []).join(" · ")
                                    color: Theme.primary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: uncertainty.modelData.reason
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                                wrapMode: Text.WordWrap
                            }
                            Flow {
                                visible: (uncertainty.modelData.credits || []).length > 0
                                Layout.fillWidth: true
                                spacing: 8
                                Repeater {
                                    model: uncertainty.modelData.credits || []
                                    delegate: TextButton {
                                        id: creditButton
                                        required property var modelData
                                        text: modelData.name + (modelData.role === "remixer"
                                            ? " · Remixer" : "")
                                            + (uncertainty.selectedIds.includes(modelData.id)
                                                ? " ✓" : "")
                                        kind: uncertainty.selectedIds.includes(modelData.id)
                                            ? "neutral" : "ghost"
                                        implicitHeight: 29
                                        onClicked: {
                                            const ids = uncertainty.selectedIds.slice()
                                            const at = ids.indexOf(modelData.id)
                                            if (at >= 0) ids.splice(at, 1)
                                            else ids.push(modelData.id)
                                            uncertainty.selectedIds = ids
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                visible: (uncertainty.modelData.credits || []).length > 0
                                Layout.fillWidth: true
                                Text {
                                    Layout.fillWidth: true
                                    text: "Only the selected artists receive these genres"
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }
                                TextButton {
                                    text: "Apply choice"
                                    kind: "neutral"
                                    enabledAction: uncertainty.selectedIds.length > 0
                                        && !page.state.busy
                                    onClicked: page.manager.chooseArtistContributors(
                                        uncertainty.modelData.trackId,
                                        uncertainty.selectedIds
                                    )
                                }
                            }
                        }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: Theme.separator
                        }
                    }
                }
            }
        }
        Text {
            visible: !!page.state.error
            Layout.fillWidth: true
            Layout.leftMargin: page.marginSize
            Layout.rightMargin: page.marginSize
            Layout.topMargin: 10
            Layout.bottomMargin: 10
            text: page.state.error
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }
}
