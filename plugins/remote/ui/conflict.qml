import QtQuick
import QtQuick.Controls.Basic
import Mtee

// One conflict of MTEE Remote, as a tab of a center window (plan 126.6, MTEE 0.3.0 layout). Same
// page layout as the Tasks window: a SectionLabel, the title, a TagChip for the state, then
// surface cards with the control radius. Both versions are two columns on one card; differing
// rows are in the warning colour. Nothing changes until a choice is pressed. After a choice the
// outcome is shown and Close closes the tab in its window (``groupId``, which stays the same when
// windows are split or moved; ``groupIndex`` is not kept). The core sets workspace, tab, groupId,
// groupIndex, bottomInset and backend after loading.
Rectangle {
    id: page

    property var workspace
    property var tab
    property string groupId: ""
    property int groupIndex: 0
    property int bottomInset: 0
    property var backend

    property var view: ({})
    readonly property string conflictId: page.tab ? page.tab.ref : ""
    readonly property var thisSide: page.view.thisSide || ({ caption: "This computer", sub: "" })
    readonly property var serverSide: page.view.serverSide || ({ caption: "Server", sub: "" })
    readonly property var rows: page.view.rows || []
    readonly property var choices: page.view.choices || []
    readonly property int labelWidth: 112

    objectName: "conflictView"
    color: Theme.editor

    function reload() {
        if (!page.backend || !page.tab) return
        page.view = JSON.parse(page.backend.load(page.tab.ref))
    }

    onTabChanged: reload()
    onBackendChanged: reload()

    Connections {
        target: page.backend
        ignoreUnknownSignals: true
        function onChanged(changedId) {
            if (changedId === page.conflictId) page.reload()
        }
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.bottomMargin: page.bottomInset
        contentHeight: column.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        WheelScrollHandler { flickable: scroller }
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: column
            x: Math.max(24, (scroller.width - width) / 2)
            width: Math.min(900, scroller.width - 48)
            spacing: 14

            Item {
                width: parent.width
                height: headColumn.implicitHeight + 44

                Column {
                    id: headColumn
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 14
                    width: parent.width
                    spacing: 2

                    SectionLabel { text: "Remote · Conflict" }

                    Text {
                        objectName: "conflictTitle"
                        width: parent.width
                        text: page.view.title || page.tab && page.tab.title || ""
                        elide: Text.ElideRight
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeHeading
                        font.weight: Font.Bold
                    }

                    Text {
                        width: parent.width
                        text: page.view.summary || ""
                        elide: Text.ElideRight
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    Item { width: 1; height: 6 }

                    // The state of the conflict, as the Tasks window tags a task.
                    TagChip {
                        objectName: "conflictState"
                        visible: page.view.loading !== true
                        text: page.view.finished === true ? "Resolved" : "Waiting for you"
                        tone: page.view.finished === true ? "primary" : "warning"
                    }
                }
            }

            Rectangle {
                objectName: "conflictVersions"
                width: parent.width
                height: versions.implicitHeight + 28
                color: Theme.surface
                radius: Theme.radius

                Column {
                    id: versions
                    x: 16
                    y: 14
                    width: parent.width - 32
                    spacing: 0

                    // Column heads: which copy, where and when.
                    Row {
                        width: parent.width
                        height: 56

                        Item { width: page.labelWidth; height: 1 }

                        Repeater {
                            model: [page.thisSide, page.serverSide]
                            delegate: Column {
                                required property var modelData
                                width: (versions.width - page.labelWidth) / 2
                                spacing: 2

                                Text {
                                    objectName: "conflictSideCaption"
                                    text: modelData.caption
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeBody
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    width: parent.width - 12
                                    text: modelData.sub
                                    wrapMode: Text.WordWrap
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }
                            }
                        }
                    }

                    Repeater {
                        model: page.rows

                        delegate: Item {
                            id: line
                            required property var modelData
                            width: versions.width
                            height: 28

                            Rectangle {
                                width: parent.width
                                height: 1
                                color: Theme.separator
                            }

                            Text {
                                width: page.labelWidth
                                anchors.verticalCenter: parent.verticalCenter
                                text: line.modelData.label
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }

                            Row {
                                x: page.labelWidth
                                height: parent.height

                                Repeater {
                                    model: [line.modelData.a, line.modelData.b]
                                    delegate: Item {
                                        required property var modelData
                                        width: (versions.width - page.labelWidth) / 2
                                        height: line.height

                                        Text {
                                            objectName: "conflictValue"
                                            width: parent.width - 12
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData
                                            elide: Text.ElideRight
                                            color: line.modelData.differs ? Theme.warning : Theme.textPrimary
                                            font.family: Theme.fontFamily
                                            font.pixelSize: Theme.fontSizeSecondary
                                            font.weight: line.modelData.differs ? Font.DemiBold : Font.Normal
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // A playlist changed on both sides: both track lists, one column each (plan 126.7).
                    Row {
                        objectName: "conflictLists"
                        width: parent.width
                        visible: page.view.lists !== undefined

                        Item { width: page.labelWidth; height: 1 }

                        Repeater {
                            model: page.view.lists ? [page.view.lists.thisSide, page.view.lists.serverSide] : []
                            delegate: Column {
                                required property var modelData
                                width: (versions.width - page.labelWidth) / 2
                                spacing: 2

                                Repeater {
                                    model: modelData
                                    delegate: Text {
                                        required property string modelData
                                        width: parent.width - 12
                                        text: modelData
                                        elide: Text.ElideRight
                                        color: Theme.textPrimary
                                        font.family: Theme.fontFamily
                                        font.pixelSize: Theme.fontSizeSecondary
                                    }
                                }
                            }
                        }
                    }

                    Item { width: 1; height: 8 }

                    Row {
                        width: parent.width
                        spacing: 6
                        visible: (page.view.reason || "") !== ""

                        Icon {
                            anchors.top: parent.top
                            anchors.topMargin: 1
                            name: "alert"
                            size: 14
                            color: Theme.warning
                        }

                        Text {
                            objectName: "conflictReason"
                            width: parent.width - 20
                            text: page.view.reason || ""
                            wrapMode: Text.WordWrap
                            color: Theme.warning
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }
                }
            }

            Text {
                objectName: "conflictLoading"
                visible: page.view.loading === true || page.view.viewError !== undefined
                width: parent.width
                text: page.view.viewError !== undefined ? page.view.viewError : "Reading both versions…"
                wrapMode: Text.WordWrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            // The outcome of a choice, or what the tab waits for; then the next click closes it.
            Rectangle {
                objectName: "conflictOutcomeCard"
                visible: page.view.finished === true
                width: parent.width
                height: outcomeColumn.implicitHeight + 28
                color: Theme.surface
                radius: Theme.radius

                Column {
                    id: outcomeColumn
                    x: 16
                    y: 14
                    width: parent.width - 32
                    spacing: 12

                    Text {
                        objectName: "conflictOutcome"
                        width: parent.width
                        text: page.view.outcome || ""
                        wrapMode: Text.WordWrap
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSecondary
                    }

                    TextButton {
                        objectName: "conflictClose"
                        text: "Close"
                        kind: "ghost"
                        implicitHeight: 32
                        width: 120
                        onClicked: page.workspace.closeTab(page.groupId, page.tab.id)
                    }
                }
            }

            SectionLabel {
                visible: page.view.finished !== true && page.choices.length > 0
                text: "Choose what to keep"
            }

            Rectangle {
                objectName: "conflictChoices"
                visible: page.view.finished !== true && page.choices.length > 0
                width: parent.width
                height: choiceColumn.implicitHeight + 8
                color: Theme.surface
                radius: Theme.radius

                Column {
                    id: choiceColumn
                    x: 16
                    y: 4
                    width: parent.width - 32

                    Repeater {
                        model: page.choices

                        delegate: Item {
                            id: choice
                            required property var modelData
                            required property int index
                            width: choiceColumn.width
                            height: Math.max(48, choiceText.implicitHeight + 20)

                            Rectangle {
                                visible: choice.index > 0
                                width: parent.width
                                height: 1
                                color: Theme.separator
                            }

                            TextButton {
                                id: ghostChoice
                                objectName: "conflictChoice"
                                anchors.verticalCenter: parent.verticalCenter
                                visible: !choice.modelData.danger
                                width: 190
                                implicitHeight: 32
                                text: choice.modelData.label
                                kind: "ghost"
                                onClicked: page.backend.choose(page.conflictId, choice.modelData.action)
                            }

                            // A destructive choice is drawn red and is never the default.
                            DangerButton {
                                id: dangerChoice
                                objectName: "conflictChoiceDanger"
                                anchors.verticalCenter: parent.verticalCenter
                                visible: choice.modelData.danger
                                width: 190
                                text: choice.modelData.label
                                enabledAction: true
                                onClicked: page.backend.choose(page.conflictId, choice.modelData.action)
                            }

                            Text {
                                id: choiceText
                                anchors.left: ghostChoice.right
                                anchors.leftMargin: 20
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: choice.modelData.text
                                wrapMode: Text.WordWrap
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }
                    }
                }
            }

            Text {
                objectName: "conflictError"
                visible: (page.view.error || "") !== ""
                width: parent.width
                text: page.view.error || ""
                wrapMode: Text.WordWrap
                color: Theme.warning
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            Text {
                width: parent.width
                visible: page.view.finished !== true
                text: "Nothing changes until you choose."
                color: Theme.textMuted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }
    }
}
