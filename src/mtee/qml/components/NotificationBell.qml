import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The notifications bell of the header (plan 134.4, U9) and its balloon (P9). The badge counts the
// unread notifications, the tag conflicts and the items plugins leave to the user. The drop-down
// lists what waits for the user, then the notifications of this session, newest first; opening it
// marks them read. A new notification, or a message of the workspace, shows a balloon under the bell
// for 5 s (hover keeps it), so no toast covers the player.
Item {
    id: bell

    required property var workspace
    readonly property var conflicts: workspace.tagConflicts
    readonly property int conflictCount: conflicts && typeof conflicts.count === "number"
        ? conflicts.count : 0
    readonly property var pluginUi: workspace.pluginUi || null
    readonly property int waitingCount: pluginUi !== null ? pluginUi.waitingCount : 0
    readonly property int waitingTotal: conflictCount + waitingCount
    // The id of the newest notification the balloon has shown (or seen at start).
    property string lastShownId: ""

    objectName: "notificationBell"

    Component.onCompleted: {
        const latest = notifications.latest
        lastShownId = latest && latest.id !== undefined ? String(latest.id) : ""
    }

    function ageText(createdAt) {
        const seconds = Math.max(0, Date.now() / 1000 - createdAt)
        if (seconds < 60)
            return "Just now"
        const minutes = Math.floor(seconds / 60)
        if (minutes < 60)
            return minutes + " min ago"
        const hours = Math.floor(minutes / 60)
        if (hours < 24)
            return hours + " h ago"
        return Math.floor(hours / 24) + " d ago"
    }

    HeaderButton {
        id: button
        objectName: "notificationButton"
        anchors.fill: parent
        icon: "bell"
        tip: "Notifications"
        badge: notifications.unreadCount + bell.waitingTotal
        active: popover.opened
        onClicked: popover.toggle()
    }

    Popover {
        id: popover
        objectName: "notificationPopover"
        anchorItem: button
        bodyWidth: 380
        maxHeight: 560
        onOpened: {
            balloon.hide()
            notifications.markAllRead()
        }

        Column {
            id: list
            width: parent.width
            spacing: 16

            // What waits for the user: tag conflicts, then each plugin group (hidden when empty).
            Column {
                id: waitingSection
                objectName: "waitingSection"
                width: list.width
                spacing: 10
                visible: bell.waitingTotal > 0

                SectionLabel {
                    text: "Waiting for you"
                }

                // The tag conflicts with their bulk actions (replace all, dismiss all).
                Item {
                    objectName: "tagConflictsHeader"
                    visible: bell.conflictCount > 0
                    width: waitingSection.width
                    height: 24

                    SectionLabel {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Tag conflicts (" + bell.conflictCount + ")"
                    }

                    Row {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2

                        IconButton {
                            objectName: "replaceAllConflicts"
                            width: 22
                            height: 22
                            icon: "check"
                            iconSize: 14
                            tip: "Replace all: delete the old tag values of every listed track and write the new ones"
                            onClicked: bell.conflicts.resolveAll()
                        }

                        IconButton {
                            objectName: "dismissAllConflicts"
                            width: 22
                            height: 22
                            icon: "close"
                            iconSize: 14
                            tip: "Dismiss all without writing"
                            onClicked: bell.conflicts.dismissAll()
                        }
                    }
                }

                Repeater {
                    id: conflictRepeater
                    model: bell.conflictCount > 0 ? bell.conflicts : null

                    delegate: TaskConflictRow {
                        required property string trackId
                        required property string fileName
                        required property string summary
                        required property string conflictState
                        required property string errorMessage

                        width: waitingSection.width
                        title: fileName
                        detail: summary
                        stage: conflictState
                        error: errorMessage
                        onReplaceRequested: bell.conflicts.resolve(trackId)
                        onDismissRequested: bell.conflicts.dismiss(trackId)
                    }
                }

                Repeater {
                    model: bell.pluginUi !== null ? bell.pluginUi.waitingGroups : []

                    delegate: Column {
                        id: group

                        required property var modelData

                        objectName: "bellWaitingGroup"
                        visible: groupRepeater.count > 0
                        width: waitingSection.width
                        spacing: 8

                        SectionLabel {
                            text: group.modelData.title + " (" + groupRepeater.count + ")"
                        }

                        Repeater {
                            id: groupRepeater
                            model: bell.pluginUi.waitingModel(group.modelData.key)

                            delegate: TaskChoiceRow {
                                required property var modelData

                                width: group.width
                                title: modelData.title || ""
                                detail: modelData.subtitle || ""
                                actionText: modelData.action || "Open"
                                onChosen: bell.pluginUi.runWaiting(group.modelData.key, modelData.id)
                                onDismissRequested: bell.pluginUi.dismissWaiting(group.modelData.key, modelData.id)
                            }
                        }
                    }
                }
            }

            // The notifications of this session, newest first.
            Column {
                id: noteSection
                width: list.width
                spacing: 8

                Item {
                    width: parent.width
                    height: 24

                    SectionLabel {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Notifications"
                    }

                    TextButton {
                        objectName: "notificationsClear"
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Clear"
                        kind: "ghost"
                        implicitHeight: 24
                        enabledAction: noteRepeater.count > 0
                        onClicked: notifications.clear()
                    }
                }

                Text {
                    objectName: "notificationsEmpty"
                    visible: noteRepeater.count === 0
                    width: parent.width
                    text: "No notifications in this session."
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    wrapMode: Text.WordWrap
                }

                Repeater {
                    id: noteRepeater
                    model: notifications

                    delegate: Column {
                        id: note

                        required property var model

                        objectName: "notificationRow"
                        width: noteSection.width
                        spacing: 3

                        Text {
                            width: parent.width
                            text: note.model.text
                            wrapMode: Text.WordWrap
                            color: note.model.tone === "warning" ? Theme.warning : Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSecondary
                        }

                        Row {
                            spacing: 8

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: bell.ageText(note.model.createdAt)
                                color: Theme.textMuted
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }

                            TextButton {
                                objectName: "notificationDetails"
                                text: "Details"
                                kind: "ghost"
                                implicitHeight: 24
                                onClicked: notifications.openDetails(note.model.id)
                            }
                        }
                    }
                }
            }
        }
    }

    // The balloon (P9): a notification or a workspace message, under the bell, for 5 s.
    WindowSurface {
        id: balloon
        objectName: "notificationBalloon"
        parent: Overlay.overlay
        z: 60
        padding: 12
        cornerColor: Theme.chrome
        width: Math.min(340, (parent ? parent.width : 340) - 16)
        height: balloonColumn.implicitHeight + 2 * padding
        opacity: showing ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 250 } }

        property bool showing: false
        // "notification" (with Details) or "message" (the workspace text, cleared when it hides).
        property string mode: "notification"
        property string headline: ""
        property string notificationId: ""

        function place() {
            const root = Overlay.overlay
            if (!root)
                return
            const origin = button.mapToItem(root, 0, button.height)
            x = Math.max(8, Math.min(root.width - width - 8, origin.x + button.width - width))
            y = origin.y + 6
        }

        function showNotification(row) {
            mode = "notification"
            headline = String(row.text)
            notificationId = String(row.id)
            present()
        }

        function showMessage(text) {
            mode = "message"
            headline = text
            notificationId = ""
            present()
        }

        function present() {
            place()
            showing = true
            hideTimer.restart()
        }

        function hide() {
            if (!showing)
                return
            showing = false
            if (mode === "message" && bell.workspace.message.length > 0)
                bell.workspace.clearMessage()
        }

        Column {
            id: balloonColumn
            objectName: "notificationBalloonText"
            width: parent.width
            spacing: 8

            Text {
                width: parent.width
                text: balloon.headline
                wrapMode: Text.WordWrap
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            TextButton {
                objectName: "notificationBalloonDetails"
                visible: balloon.notificationId.length > 0
                text: "Details"
                kind: "ghost"
                implicitHeight: 24
                onClicked: {
                    notifications.openDetails(balloon.notificationId)
                    balloon.hide()
                }
            }
        }

        HoverHandler {
            id: balloonHover
        }

        Timer {
            id: hideTimer
            interval: 5000
            running: balloon.showing && !balloonHover.hovered
            onTriggered: balloon.hide()
        }
    }

    Connections {
        target: notifications
        function onCountsChanged() {
            const latest = notifications.latest
            if (!latest || latest.id === undefined)
                return
            const id = String(latest.id)
            if (id === bell.lastShownId)
                return
            bell.lastShownId = id
            if (!popover.opened)
                balloon.showNotification(latest)
        }
    }

    Connections {
        target: bell.workspace
        function onMessageChanged() {
            const text = bell.workspace.message
            if (text.length === 0) {
                if (balloon.mode === "message")
                    balloon.showing = false
                return
            }
            if (!shell.demoMode && !popover.opened)
                balloon.showMessage(text)
        }
    }
}
