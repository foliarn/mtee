import QtQuick
import Mtee

// Settings > Remote: the server, this computer, the devices of the account, the sync, playback,
// backups, the settings that travel and the folders that sync with the server (plans 126 and 127).
// Built from the rows of Mtee (MTEE 0.3.0): Group, FieldRow, ToggleRow, StepperRow, ActionRow, the
// plugin's ChoiceRow for the chip choices, TagChip for a tag and one ConfirmDialog for the actions
// that cannot be undone from here (revoke a device, delete a backup). ``workspace`` and ``backend``
// are set by the core after loading, so every binding reads ``backend`` with a fallback.
Column {
    id: page

    property var workspace
    property var backend
    property string serverText: backend ? backend.serverUrl : ""
    property string userText: backend ? backend.userName : ""
    property string deviceText: backend ? backend.deviceName : ""
    readonly property bool signedIn: backend ? backend.signedIn : false
    readonly property bool busy: backend ? backend.busy : false
    readonly property bool connected: backend ? backend.connected : false
    readonly property string syncMode: backend ? backend.syncMode : "auto"
    readonly property int idleDelay: backend ? backend.idleDelay : 120
    readonly property int pendingCount: backend ? backend.pendingCount : 0
    readonly property bool autoPull: backend ? backend.autoPull : false
    readonly property bool downloadNew: backend ? backend.downloadNew : false
    readonly property string streamLevel: backend ? backend.streamLevel : "original"
    // The folder being linked (its path), and the choice made in its editor.
    property string editingPath: ""
    property string editRootId: ""
    property string editLocalSubpath: ""
    property string editSubpath: ""

    objectName: "remoteSettingsPage"
    spacing: 8

    onConnectedChanged: if (connected) page.backend.loadFolders()
    Component.onCompleted: if (connected) page.backend.loadFolders()

    function connectNow() {
        page.backend.connectTo(page.serverText, page.userText, passwordRow.text, page.deviceText)
        passwordRow.clear()
    }

    // The one question of the page: revoke a device, or delete a backup. ``pending`` names it.
    function ask(kind, id, name) {
        confirm.pending = { "kind": kind, "id": id }
        if (kind === "revoke") {
            confirm.title = "Revoke " + name + "?"
            confirm.text = "That device is signed out of your account at once. It can connect again with your password."
            confirm.buttons = [{ "key": "cancel", "label": "Cancel", "kind": "ghost" },
                               { "key": "confirm", "label": "Revoke", "kind": "danger" }]
        } else {
            confirm.title = "Delete this backup?"
            confirm.text = name + ". It moves to the server's trash and leaves this list."
            confirm.buttons = [{ "key": "cancel", "label": "Cancel", "kind": "ghost" },
                               { "key": "confirm", "label": "Delete backup", "kind": "danger" }]
        }
        confirm.open()
    }

    function openEditor(row) {
        page.editingPath = row.path
        page.editRootId = row.mapped ? row.rootId : ""
        page.editLocalSubpath = row.mapped ? row.localSubpath : ""
        page.editSubpath = row.mapped ? row.subpath : ""
    }

    Group {
        objectName: "remoteGroupServer"
        title: "Server"
    }

    FieldRow {
        objectName: "remoteServer"
        label: "Server address"
        description: "The address of your MTEE Remote server. It must start with https."
        placeholder: "https://music.example.net"
        value: page.backend ? page.backend.serverUrl : ""
        onEdited: (text) => page.serverText = text
    }

    FieldRow {
        objectName: "remoteUser"
        label: "User name"
        description: "The account you were given on the server."
        value: page.backend ? page.backend.userName : ""
        onEdited: (text) => page.userText = text
    }

    PasswordRow {
        id: passwordRow
        objectName: "remotePassword"
        label: "Password"
        description: "Asked once, to connect. It is never saved on this computer."
        placeholder: "Your password"
        visible: !page.signedIn
    }

    ActionRow {
        objectName: "remoteConnection"
        label: "Connection"
        description: page.signedIn
            ? "Disconnecting signs this computer out and revokes its device key."
            : "Connecting signs this computer in and registers it as a device."
        detail: page.backend ? page.backend.stateText : ""
        actionText: page.signedIn ? "Disconnect" : "Connect"
        actionKind: page.signedIn ? "ghost" : "primary"
        enabledAction: !page.busy
        onAction: page.signedIn ? page.backend.disconnectFromServer() : page.connectNow()
    }

    Group {
        objectName: "remoteGroupComputer"
        title: "This computer"
    }

    FieldRow {
        objectName: "remoteDeviceName"
        label: "Device name"
        description: "How this computer appears in the list of devices on the server."
        value: page.backend ? page.backend.deviceName : ""
        onEdited: (text) => {
            page.deviceText = text
            page.backend.setDeviceName(text)
        }
    }

    Text {
        objectName: "remoteDevicesHeading"
        visible: deviceList.count > 0
        text: "Devices signed in to your account"
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Repeater {
        id: deviceList
        model: page.backend ? page.backend.devices : []

        delegate: Item {
            id: deviceRow
            required property var modelData

            objectName: "remoteDevice"
            width: page.width
            height: 56

            Column {
                anchors.left: parent.left
                anchors.right: revokeButton.left
                anchors.rightMargin: 24
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Row {
                    spacing: 8

                    Text {
                        text: deviceRow.modelData.name
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeBody
                    }

                    TagChip {
                        objectName: "remoteDeviceCurrent"
                        visible: deviceRow.modelData.current
                        anchors.verticalCenter: parent.verticalCenter
                        text: "This computer"
                        tone: "primary"
                    }
                }

                Text {
                    text: deviceRow.modelData.kindText + " · " + deviceRow.modelData.lastSeen
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            TextButton {
                id: revokeButton
                objectName: "remoteRevoke"
                visible: !deviceRow.modelData.current
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "Revoke"
                kind: "ghost"
                enabledAction: !page.busy
                onClicked: page.ask("revoke", deviceRow.modelData.deviceId, deviceRow.modelData.name)
            }
        }
    }

    // Sync: the push of this computer (plan 126.3). Auto sends on its own once a file has settled;
    // Manual queues the changes until Apply. The fetch from the server is plan 126.4, below.
    Group {
        objectName: "remoteGroupSync"
        title: "Sync"
    }

    ChoiceRow {
        objectName: "remoteSyncMode"
        label: "Sync mode"
        description: "Auto sends new tracks, tag edits, moves and renames on its own. Manual keeps them in a queue until you press Apply."
        options: [{ "key": "auto", "label": "Auto", "name": "remoteSyncAuto" },
                  { "key": "manual", "label": "Manual", "name": "remoteSyncManual" }]
        current: page.syncMode
        onChosen: (key) => page.backend.setSyncMode(key)
    }

    StepperRow {
        objectName: "remoteIdleDelay"
        label: "File idle delay (minutes)"
        description: "Auto mode waits until a file has not changed for this long, so a file still being written is not sent half done."
        value: Math.round(page.idleDelay / 60)
        from: 0
        to: 60
        step: 1
        onChosen: (value) => page.backend.setIdleDelayMinutes(value)
    }

    ActionRow {
        objectName: "remoteApplyPending"
        visible: page.syncMode === "manual"
        label: "Pending changes"
        description: "Changes of this computer that wait for you. Nothing is sent in Manual mode until you press Apply."
        actionText: "Apply pending changes (" + page.pendingCount + ")"
        actionKind: "primary"
        enabledAction: !page.busy && page.pendingCount > 0
        onAction: page.backend.applyPending()
    }

    // Server to computer (plan 126.4): Auto pull follows the server as changes come; otherwise a
    // change of another device reaches this computer on Fetch.
    ToggleRow {
        objectName: "remoteAutoPull"
        label: "Auto pull"
        description: "Bring in the changes of your other devices on their own, as the server reports them. Off: press Fetch."
        checked: page.autoPull
        onToggled: (value) => page.backend.setAutoPull(value)
    }

    ToggleRow {
        objectName: "remoteDownloadNew"
        label: "Download new server tracks"
        description: "A track added on another device is downloaded into its mapped folder. Off: it shows as Server only, and plays after a download."
        checked: page.downloadNew
        onToggled: (value) => page.backend.setDownloadNew(value)
    }

    ActionRow {
        objectName: "remoteFetch"
        visible: page.connected
        label: "Changes from the server"
        description: "Apply what changed on the server since the last fetch: new tracks, tag edits, moves and deletions of your other devices."
        actionText: page.backend && page.backend.fetching ? "Fetching…" : "Fetch"
        actionKind: "ghost"
        enabledAction: !page.busy && !(page.backend && page.backend.fetching)
        onAction: page.backend.fetchNow()
    }

    // Playback (plan 127.5 and 127.6): the quality of a server track that is not on this computer,
    // and the size of the copies kept here for offline play. Shown with or without a connection.
    Group {
        objectName: "remoteGroupPlayback"
        title: "Playback"
    }

    ChoiceRow {
        objectName: "remoteStreamLevel"
        label: "Quality on this computer"
        description: "The quality of a track that is not on this computer. Original plays the file as it is and keeps a copy for offline play. The other levels are converted on the server and are not kept here."
        options: [{ "key": "original", "label": "Original", "name": "remoteLevelOriginal" },
                  { "key": "lossless", "label": "Lossless", "name": "remoteLevelLossless" },
                  { "key": "320", "label": "320 kbps", "name": "remoteLevel320" },
                  { "key": "128", "label": "128 kbps", "name": "remoteLevel128" }]
        current: page.streamLevel
        onChosen: (key) => page.backend.setStreamLevel(key)
    }

    StepperRow {
        objectName: "remoteCacheSize"
        label: "Cache size (GB)"
        description: "Copies of server tracks kept on this computer for offline play. The ones played longest ago are removed first."
        value: page.backend ? page.backend.cacheGb : 10
        from: 1
        to: 200
        step: 1
        onChosen: (value) => page.backend.setCacheGb(value)
    }

    ActionRow {
        objectName: "remoteClearCache"
        label: "Stream cache"
        description: "Removes the copies kept for offline play. Your own tracks and the files of the library are not touched."
        detail: page.backend ? page.backend.cacheText : ""
        actionText: "Clear cache"
        actionKind: "ghost"
        enabledAction: !page.busy
        onAction: page.backend.clearCache()
    }

    Item {
        // Reads the size of the stream cache when the page is opened.
        objectName: "remoteCacheLoader"
        visible: false
        Component.onCompleted: if (page.backend) page.backend.refreshCache()
    }

    // Backups (plan 126.8): a copy of the database to the server, on a schedule or now. The list
    // restores (MTEE asks the person to confirm) or deletes a backup (the row asks first).
    Group {
        objectName: "remoteGroupBackups"
        visible: page.connected
        title: "Backups"
    }

    ChoiceRow {
        objectName: "remoteBackupSchedule"
        visible: page.connected
        label: "Automatic backup"
        description: "A copy of the MTEE database is sent to the server. Music files are not part of it."
        options: [{ "key": "daily", "label": "Daily", "name": "remoteBackupDaily" },
                  { "key": "weekly", "label": "Weekly", "name": "remoteBackupWeekly" },
                  { "key": "off", "label": "Off", "name": "remoteBackupOff" }]
        current: page.backend ? page.backend.backupSchedule : "off"
        onChosen: (key) => page.backend.setBackupSchedule(key)
    }

    StepperRow {
        objectName: "remoteKeepDaily"
        visible: page.connected
        label: "Daily backups kept"
        description: "Older daily backups are deleted from the server."
        value: page.backend ? page.backend.backupKeepDaily : 30
        from: 0
        to: 365
        step: 1
        onChosen: (value) => page.backend.setKeepDaily(value)
    }

    StepperRow {
        objectName: "remoteKeepWeekly"
        visible: page.connected
        label: "Weekly backups kept"
        description: "The oldest backup of each week is kept longer."
        value: page.backend ? page.backend.backupKeepWeekly : 12
        from: 0
        to: 104
        step: 1
        onChosen: (value) => page.backend.setKeepWeekly(value)
    }

    ActionRow {
        objectName: "remoteBackupNow"
        visible: page.connected
        label: "Back up now"
        description: "Send a copy of the database to the server at once."
        detail: page.backend ? page.backend.lastBackupText : ""
        actionText: page.backend && page.backend.backingUp ? "Backing up…" : "Back up now"
        actionKind: "ghost"
        enabledAction: !page.busy && !(page.backend && page.backend.backingUp)
        onAction: page.backend.backUpNow()
    }

    Item {
        // Reads the list when the page is opened while connected; a connection reads it on its own.
        objectName: "remoteBackupsLoader"
        visible: false
        Component.onCompleted: if (page.connected && page.backend) page.backend.refreshBackups()
    }

    Text {
        objectName: "remoteBackupsHeading"
        visible: backupList.count > 0
        text: "Backups on the server"
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSizeSmall
    }

    Repeater {
        id: backupList
        model: page.backend ? page.backend.backups : []

        delegate: Item {
            id: backupEntry
            required property var modelData

            objectName: "remoteBackup"
            width: page.width
            height: 56

            Column {
                anchors.left: parent.left
                anchors.right: backupButtons.left
                anchors.rightMargin: 24
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2

                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: backupEntry.modelData.when + " · " + backupEntry.modelData.kind
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                }

                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: backupEntry.modelData.device + " · " + backupEntry.modelData.size
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }
            }

            Row {
                id: backupButtons
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                TextButton {
                    objectName: "remoteRestoreBackup"
                    text: "Restore…"
                    kind: "ghost"
                    enabledAction: !page.busy
                    onClicked: page.backend.restoreBackup(backupEntry.modelData.backupId)
                }

                TextButton {
                    objectName: "remoteDeleteBackup"
                    text: "Delete…"
                    kind: "ghost"
                    enabledAction: !page.busy
                    onClicked: page.ask("delete", backupEntry.modelData.backupId,
                        backupEntry.modelData.when + " · " + backupEntry.modelData.kind)
                }
            }
        }
    }

    // Settings that travel (plan 126.7): one switch per synced setting of the core, on by default.
    // What never travels is said under the switches.
    Group {
        objectName: "remoteGroupTravel"
        title: "Settings that travel"

        Repeater {
            model: page.backend ? page.backend.travelRows : []

            delegate: ToggleRow {
                required property var modelData

                objectName: "remoteTravel_" + modelData.key
                label: modelData.label
                description: "Sent to your other devices and to the server. Off: this computer keeps its own value."
                checked: modelData.enabled
                onToggled: (value) => page.backend.setTravel(modelData.key, value)
            }
        }

        Text {
            width: parent.width
            topPadding: 4
            wrapMode: Text.WordWrap
            text: "Never travels: library folders, the audio output device, the window size and position, and the data folders."
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    // Folders: one row per watched folder of this computer, with its server folder. Shown only
    // when connected, since the server folders are read from the server.
    Group {
        objectName: "remoteGroupFolders"
        visible: page.connected
        title: "Folders"
    }

    Repeater {
        objectName: "remoteFolders"
        model: page.connected && page.backend ? page.backend.folderRows : []

        delegate: Column {
            id: folderEntry
            required property var modelData

            width: page.width
            spacing: 0

            ActionRow {
                objectName: "remoteFolder"
                width: folderEntry.width
                label: folderEntry.modelData.path
                description: folderEntry.modelData.mapped
                    ? "Synced with this server folder. Tracks are matched by their audio."
                    : "Not synced yet. Link it to a server folder to start the first match."
                detail: folderEntry.modelData.text
                actionText: folderEntry.modelData.mapped ? "Change" : "Link"
                actionKind: "ghost"
                enabledAction: !page.busy
                onAction: page.openEditor(folderEntry.modelData)
            }

            Column {
                id: editor
                visible: page.editingPath === folderEntry.modelData.path
                width: folderEntry.width
                leftPadding: 0
                topPadding: 4
                bottomPadding: 12
                spacing: 8

                Flow {
                    width: parent.width
                    spacing: 6

                    Repeater {
                        model: page.backend ? page.backend.serverRoots : []

                        delegate: FilterChip {
                            id: rootChip
                            required property var modelData
                            objectName: "remoteRootChoice"
                            text: rootChip.modelData.name
                            checked: page.editRootId === rootChip.modelData.rootId
                            onToggled: page.editRootId = rootChip.modelData.rootId
                        }
                    }
                }

                FieldRow {
                    objectName: "remoteLocalSubfolder"
                    label: "Local subfolder"
                    description: "Optional. A folder inside this watched folder, for example baile. Empty syncs the whole folder. It must exist."
                    placeholder: "Whole folder"
                    value: page.editLocalSubpath
                    onEdited: (text) => page.editLocalSubpath = text
                }

                FieldRow {
                    objectName: "remoteSubfolder"
                    label: "Server subfolder"
                    description: "Optional. A folder inside the server folder, for example Incoming. Empty links the whole folder."
                    placeholder: "Whole folder"
                    value: page.editSubpath
                    onEdited: (text) => page.editSubpath = text
                }

                Row {
                    spacing: 12

                    TextButton {
                        objectName: "remoteSaveFolder"
                        text: "Save"
                        kind: "primary"
                        enabledAction: !page.busy && page.editRootId !== ""
                        onClicked: {
                            page.backend.saveFolder(folderEntry.modelData.path, page.editRootId, page.editLocalSubpath, page.editSubpath)
                            page.editingPath = ""
                        }
                    }

                    TextButton {
                        objectName: "remoteRemoveFolder"
                        text: "Remove mapping"
                        kind: "ghost"
                        visible: folderEntry.modelData.mapped
                        enabledAction: !page.busy
                        onClicked: {
                            page.backend.removeFolder(folderEntry.modelData.path)
                            page.editingPath = ""
                        }
                    }

                    TextButton {
                        objectName: "remoteCancelFolder"
                        text: "Cancel"
                        kind: "ghost"
                        onClicked: page.editingPath = ""
                    }
                }
            }
        }
    }

    ActionRow {
        objectName: "remoteCompare"
        visible: page.connected
        label: "Compare with the server"
        description: "Match this computer's tracks with the server again and show the summary. It only adds links; nothing is removed, and nothing is sent before you press Start sync."
        actionText: "Compare"
        enabledAction: !page.busy
        onAction: page.backend.compareNow()
    }

    // The question of ``ask``: nothing is sent before the danger button is pressed.
    ConfirmDialog {
        id: confirm
        objectName: "remoteConfirm"
        property var pending: ({})
        onAnswered: (key) => {
            const asked = confirm.pending
            confirm.pending = ({})
            if (key !== "confirm" || !page.backend)
                return
            if (asked.kind === "revoke")
                page.backend.revoke(asked.id)
            else if (asked.kind === "delete")
                page.backend.deleteBackup(asked.id)
        }
    }
}
