import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window
import Mtee

// The summary of the first match (plan 126.2), in the PluginDialog of the core: its width is
// 640 px (plugins/remote/__init__.py), so the content is 600 px wide. Five groups with their counts,
// each unfolding its rows. The groups scroll inside the window: the title, the intro, the footer
// and the buttons always stay in view, so Start sync and Cancel are always reachable.
// Nothing moves before "Start sync"; Cancel writes nothing. The core sets backend, ref and dialog
// after loading, so every binding reads them with a fallback.
Column {
    id: summary

    property var workspace
    property var backend
    property var ref
    property var dialog

    readonly property var groups: summary.backend ? summary.backend.groups : []

    // The popup holds its content inside the window less 72 px (16 px of margin, then 20 px of
    // padding above and below the content). The groups get what the other parts leave.
    readonly property real windowHeight: summary.Window.window ? summary.Window.window.height : 800
    readonly property real otherHeight: titleText.height + introText.height
        + footerRow.height + buttonRow.height + 4 * summary.spacing
    readonly property real groupsAvailable: Math.max(0, summary.windowHeight - 72 - summary.otherHeight)

    objectName: "firstMatchDialog"
    width: 600
    spacing: 14

    // The choice the backend keeps for "Tags differ", with what it does, in one line.
    function choiceText(key) {
        if (key === "server")
            return "This computer's files take the server's tags, names and folders. Only the tags are downloaded."
        if (key === "later")
            return "Each track waits in Conflicts until you choose. Nothing is sent for them."
        return "The server's copies take this computer's tags, names and folders. Only the tags are sent."
    }

    Text {
        id: titleText
        width: parent.width
        text: "Match with the server"
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: 24
        font.weight: Font.Bold
    }

    Text {
        id: introText
        objectName: "firstMatchIntro"
        width: parent.width
        wrapMode: Text.WordWrap
        text: summary.backend ? summary.backend.intro : ""
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSecondary
    }

    // The groups scroll here. The area is as tall as the groups, or as tall as the window leaves
    // room for, whichever is smaller; the bar is the thin one the other lists use.
    Flickable {
        id: scroll
        objectName: "firstMatchScroll"
        width: parent.width
        height: Math.min(groupList.implicitHeight, summary.groupsAvailable)
        contentWidth: width
        contentHeight: groupList.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ThinScrollBar {}

        Column {
            id: groupList
            // Narrower than the area by the bar's width, so the bar does not sit over the rows.
            width: scroll.width - 12

            Repeater {
                model: summary.groups

                delegate: Column {
                    id: group
                    required property var modelData

                    objectName: "firstMatchGroup"
                    width: groupList.width

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

                        // Tags differ: one choice for the whole group, which the conflicts and the
                        // sync will read. The choice is only recorded for now; Start sync does not
                        // act on it yet. The block is hidden in the other groups: a hidden item
                        // takes no room in the column. (A Loader here left the rows over the
                        // chips, because its height did not follow the block.)
                        Column {
                            visible: group.modelData.choose === true
                            width: parent.width - parent.leftPadding - parent.rightPadding
                            spacing: 6
                            bottomPadding: 8

                            Flow {
                                width: parent.width
                                spacing: 6

                                Text {
                                    topPadding: 5
                                    text: "When the tags differ"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }
                                FilterChip {
                                    objectName: "firstMatchChoice_computer"
                                    text: "This computer wins"
                                    checked: summary.backend ? summary.backend.choice === "computer" : false
                                    onToggled: summary.backend.setChoice("computer")
                                }
                                FilterChip {
                                    objectName: "firstMatchChoice_server"
                                    text: "Server wins"
                                    checked: summary.backend ? summary.backend.choice === "server" : false
                                    onToggled: summary.backend.setChoice("server")
                                }
                                FilterChip {
                                    objectName: "firstMatchChoice_later"
                                    text: "Decide one by one"
                                    checked: summary.backend ? summary.backend.choice === "later" : false
                                    onToggled: summary.backend.setChoice("later")
                                }
                            }

                            Text {
                                objectName: "firstMatchChoiceText"
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: summary.choiceText(summary.backend ? summary.backend.choice : "")
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }

                        Repeater {
                            model: group.modelData.items

                            // One track per row: its name, then the server's path when it differs.
                            // The width is the room inside the list's padding, so a long name is
                            // elided rather than running past the dialog.
                            delegate: Column {
                                id: entry
                                required property var modelData

                                objectName: "firstMatchRow"
                                width: parent.width - parent.leftPadding - parent.rightPadding
                                bottomPadding: 6

                                Text {
                                    width: parent.width
                                    text: entry.modelData.name
                                    elide: Text.ElideMiddle
                                    color: Theme.textPrimary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeSmall
                                }

                                Text {
                                    visible: entry.modelData.note !== ""
                                    width: parent.width
                                    text: entry.modelData.note
                                    elide: Text.ElideMiddle
                                    color: Theme.textSecondary
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.fontSizeCaption
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
    }

    Row {
        id: footerRow
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
        id: buttonRow
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
