import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The summary of the first match (plan 126.2), in the PluginDialog of the core: its width is
// 480 px, so the content is 440 px wide. Five groups with their counts, each unfolding its rows.
// Nothing moves before "Start sync"; Cancel writes nothing. The core sets backend, ref and dialog
// after loading, so every binding reads them with a fallback.
Column {
    id: summary

    property var workspace
    property var backend
    property var ref
    property var dialog

    readonly property var groups: summary.backend ? summary.backend.groups : []

    objectName: "firstMatchDialog"
    width: 440
    spacing: 14

    Text {
        width: parent.width
        text: "Match with the server"
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 24
        font.weight: Font.Bold
    }

    Text {
        objectName: "firstMatchIntro"
        width: parent.width
        wrapMode: Text.WordWrap
        text: summary.backend ? summary.backend.intro : ""
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    Column {
        width: parent.width

        Repeater {
            model: summary.groups

            delegate: Column {
                id: group
                required property var modelData

                objectName: "firstMatchGroup"
                width: summary.width

                Rectangle { width: parent.width; height: 1; color: Theme.separator }

                Item {
                    id: head
                    width: parent.width
                    height: 52

                    MouseArea {
                        objectName: "firstMatchToggle"
                        anchors.fill: parent
                        onClicked: summary.backend.toggle(group.modelData.key)
                    }

                    Icon {
                        x: 0
                        anchors.verticalCenter: parent.verticalCenter
                        name: group.modelData.open ? "chevron-down" : "chevron-right"
                        size: 16
                        color: Theme.textSecondary
                    }

                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 26
                        anchors.right: count.left
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 1

                        Text {
                            text: group.modelData.label
                            color: Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                        }

                        Text {
                            width: parent.width
                            wrapMode: Text.WordWrap
                            text: group.modelData.text
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }

                    Text {
                        id: count
                        objectName: "firstMatchCount"
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: group.modelData.count
                        color: group.modelData.tone === "warning" ? Theme.warning
                            : group.modelData.tone === "secondary" ? Theme.secondary
                            : Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeTitle
                        font.weight: Font.DemiBold
                    }
                }

                Column {
                    visible: group.modelData.open === true
                    width: parent.width
                    leftPadding: 26
                    bottomPadding: 10

                    // Tags differ: the choice of a side comes with the conflicts; only "Decide later"
                    // can be chosen here, so nothing changes until the person decides.
                    Row {
                        visible: group.modelData.choose === true
                        spacing: 6
                        bottomPadding: 8

                        Text {
                            topPadding: 5
                            text: "Keep"
                            color: Theme.textSecondary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                        FilterChip { enabled: false; opacity: 0.45; implicitHeight: 28; text: "This computer's tags" }
                        FilterChip { enabled: false; opacity: 0.45; implicitHeight: 28; text: "The server's tags" }
                        FilterChip { implicitHeight: 28; text: "Decide later"; checked: true }
                    }

                    Repeater {
                        model: group.modelData.items

                        delegate: Item {
                            id: entry
                            required property var modelData

                            width: parent.width
                            height: 26

                            Text {
                                anchors.left: parent.left
                                anchors.right: note.left
                                anchors.rightMargin: 12
                                anchors.verticalCenter: parent.verticalCenter
                                text: entry.modelData.name
                                elide: Text.ElideMiddle
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }

                            Text {
                                id: note
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(implicitWidth, parent.width * 0.5)
                                text: entry.modelData.note
                                elide: Text.ElideRight
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }
                    }

                    Text {
                        visible: (group.modelData.more || 0) > 0
                        topPadding: 4
                        text: "and " + group.modelData.more + " more"
                        color: Theme.textMuted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeSmall
                    }
                }
            }
        }

        Rectangle { width: parent.width; height: 1; color: Theme.separator }
    }

    Row {
        width: parent.width
        spacing: 6

        Icon {
            name: "info"
            size: 14
            color: Theme.textSecondary
        }

        Text {
            width: parent.width - 20
            wrapMode: Text.WordWrap
            text: summary.backend ? summary.backend.footer : ""
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    // Right to left: the first child is the rightmost button, the primary one.
    Row {
        width: parent.width
        layoutDirection: Qt.RightToLeft
        spacing: 12

        TextButton {
            objectName: "firstMatchStart"
            text: "Start sync"
            kind: "primary"
            enabledAction: summary.backend ? summary.backend.hasReport : false
            onClicked: {
                summary.backend.startSync()
                summary.dialog.close()
            }
        }

        TextButton {
            objectName: "firstMatchCancel"
            text: "Cancel"
            kind: "ghost"
            onClicked: {
                summary.backend.discard()
                summary.dialog.close()
            }
        }
    }
}
