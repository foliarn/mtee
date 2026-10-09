import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Mtee
import "../components"

Rectangle {
    id: page
    required property var manager
    required property var workspace
    readonly property var state: manager ? manager.state : ({})
    readonly property var preview: state.organizePreview || ({})
    property bool requested: false
    readonly property int marginSize: width < 700 ? 18 : 32

    objectName: "genreOrganizePage"
    color: Theme.editor

    function genreName(identity) {
        for (const genre of state.genres || [])
            if (genre.genre_id === identity)
                return genre.name
        return "Genre"
    }

    function destinationGroups() {
        const seen = new Set()
        const rows = []
        for (const item of preview.rows || []) {
            if (!item.rootId || !item.genreId) continue
            const key = item.rootId + ":" + item.genreId
            if (seen.has(key)) continue
            seen.add(key)
            rows.push(item)
        }
        return rows
    }

    function requestPreview() {
        if (!requested && state.sessionId && !state.busy) {
            requested = true
            manager.openOrganize()
        }
    }

    Component.onCompleted: requestPreview()
    Connections {
        target: manager
        function onChanged() { page.requestPreview() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: page.marginSize
            Layout.rightMargin: page.marginSize
            Layout.topMargin: 27
            Layout.bottomMargin: 21
            spacing: 9
            SectionLabel { text: "GENRE MANAGER" }
            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Text {
                    text: "Organize files"
                    color: Theme.textPrimary
                    font.family: Theme.displayFontFamily
                    font.pixelSize: Theme.fontSizeHeading
                    font.weight: Font.Bold
                }
                Item { Layout.fillWidth: true }
                TextButton {
                    text: "Back to classify"
                    kind: "ghost"
                    onClicked: page.workspace.openGenreManagerView("classify", "Genre Manager")
                }
            }
            Text {
                Layout.fillWidth: true
                text: (page.preview.reviewed || 0) + " reviewed tracks in "
                    + (page.state.sourceLabel || "this source") + " · "
                    + (page.preview.unreviewed || 0) + " left to review"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }
            Text {
                Layout.fillWidth: true
                text: "Only reviewed tracks with an explicit destination can move. "
                    + "Other apps using file paths will not be updated."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
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
                ColumnLayout {
                    visible: page.destinationGroups().length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: page.marginSize
                    Layout.rightMargin: page.marginSize
                    Layout.topMargin: 20
                    Layout.bottomMargin: 18
                    spacing: 12
                    Text {
                        text: "CHOOSE DESTINATIONS"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        font.letterSpacing: 1.2
                    }
                    Repeater {
                        model: page.destinationGroups()
                        delegate: RowLayout {
                            id: mappingRow
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 12
                            ColumnLayout {
                                Layout.preferredWidth: 240
                                Layout.minimumWidth: 240
                                Layout.maximumWidth: 240
                                spacing: 3
                                Text {
                                    Layout.fillWidth: true
                                    text: page.genreName(mappingRow.modelData.genreId)
                                        + " · " + mappingRow.modelData.rootName
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSecondary
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: mappingRow.modelData.rootPath
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                    elide: Text.ElideMiddle
                                }
                            }
                            TextField {
                                id: destinationField
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                placeholderText: "Folder within this library root"
                                text: mappingRow.modelData.relativeFolder || ""
                                color: Theme.textPrimary
                                placeholderTextColor: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSecondary
                                selectByMouse: true
                                background: Rectangle {
                                    color: Theme.surface
                                    border.width: 1
                                    border.color: destinationField.activeFocus
                                        ? Theme.focus : Theme.separator
                                }
                                onAccepted: page.manager.setDestination(
                                    mappingRow.modelData.rootId,
                                    mappingRow.modelData.genreId,
                                    text
                                )
                            }
                            TextButton {
                                id: saveMapping
                                text: "Use folder"
                                kind: "neutral"
                                enabledAction: !page.state.busy
                                onClicked: page.manager.setDestination(
                                    mappingRow.modelData.rootId,
                                    mappingRow.modelData.genreId,
                                    destinationField.text
                                )
                            }
                        }
                    }
                }
                Rectangle {
                    visible: page.destinationGroups().length > 0
                    Layout.fillWidth: true
                    height: 1
                    color: Theme.separator
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: page.marginSize
                    Layout.rightMargin: page.marginSize
                    Layout.topMargin: 18
                    Layout.bottomMargin: 12
                    Text {
                        text: "PREVIEW"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                        font.letterSpacing: 1.2
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: (page.preview.ready || 0) + " ready"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }
                Repeater {
                    model: page.preview.rows || []
                    delegate: Rectangle {
                        id: previewRow
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 74
                        color: "transparent"
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: page.marginSize
                            anchors.rightMargin: page.marginSize
                            spacing: 18
                            ColumnLayout {
                                Layout.preferredWidth: Math.max(240, previewRow.width * 0.48)
                                Layout.maximumWidth: Math.max(240, previewRow.width * 0.48)
                                spacing: 4
                                Text {
                                    Layout.fillWidth: true
                                    text: previewRow.modelData.title
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSecondary
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: previewRow.modelData.source
                                    color: Theme.textMuted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                    elide: Text.ElideMiddle
                                }
                            }
                            Text {
                                Layout.preferredWidth: Math.max(130, previewRow.width * 0.27)
                                text: previewRow.modelData.destination || "—"
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                                elide: Text.ElideMiddle
                            }
                            Text {
                                Layout.preferredWidth: 126
                                text: previewRow.modelData.status === "ready"
                                    ? (previewRow.modelData.needsFolder ? "Create folder · Ready" : "Ready")
                                    : previewRow.modelData.message || previewRow.modelData.status
                                color: previewRow.modelData.status === "ready"
                                    ? Theme.primary : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                                elide: Text.ElideRight
                            }
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.separator }
                    }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.separator }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: page.marginSize
            Layout.rightMargin: page.marginSize
            Layout.topMargin: 12
            Layout.bottomMargin: 12
            spacing: 10
            Text {
                Layout.fillWidth: true
                text: page.state.error || (page.state.organizeResult.moved !== undefined
                    ? page.state.organizeResult.moved + " moved · "
                        + page.state.organizeResult.conflicts + " conflicts · "
                        + page.state.organizeResult.busy + " busy"
                    : page.state.message || "Review every destination before moving")
                color: page.state.error ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
                elide: Text.ElideRight
            }
            TextButton {
                visible: page.state.organizeMoving
                text: "Cancel remaining"
                kind: "ghost"
                onClicked: page.manager.cancelOrganization()
            }
            TextButton {
                text: "Undo organization"
                kind: "ghost"
                enabledAction: page.state.canUndoOrganization && !page.state.busy
                onClicked: page.manager.undoOrganization()
            }
            TextButton {
                text: page.preview.undoOf ? "Move " + (page.preview.ready || 0) + " files back"
                    : "Move " + (page.preview.ready || 0) + " files"
                kind: "primary"
                enabledAction: page.preview.ready > 0 && !page.state.busy
                    && !page.state.organizeResult.operationId
                onClicked: page.manager.moveReviewedFiles()
            }
        }
    }
}
