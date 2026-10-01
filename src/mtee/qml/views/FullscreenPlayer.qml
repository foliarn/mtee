import QtQuick
import QtQuick.Controls.Basic
import Mtee
import "../components"

// Fullscreen player: source at the top, large cover and identity, waveform
// placeholder and transport. It follows the playing track, not the selection.
Rectangle {
    id: player

    required property var workspace
    required property var metadataEditor
    readonly property var playback: workspace.playerModel
    readonly property var waveform: playback.waveformModel
    readonly property var track: playback.playingTrack
    property bool showTags: false
    onShowTagsChanged: refreshTagFields()

    objectName: "fullscreenPlayer"
    color: Theme.editor

    function time(seconds) {
        const total = Math.max(0, Math.floor(seconds))
        const minutes = Math.floor(total / 60)
        const secs = total % 60
        return minutes + ":" + (secs < 10 ? "0" : "") + secs
    }

    function recoveryForPlayingTrack() {
        if (player.metadataEditor === null)
            return []
        return player.metadataEditor.recoveryOperations.filter(function(operation) {
            return operation.situation === "inspection_failed"
                || operation.trackId === player.playback.playingId
        })
    }

    function refreshTagFields() {
        if (player.metadataEditor === null)
            return
        if (player.showTags && player.playback.playingId.length > 0) {
            player.metadataEditor.prepareTrackInspection(player.playback.playingId)
            tagEditor.refreshFields()
        } else {
            player.metadataEditor.cancelPendingInspection()
            tagEditor.refreshFields()
        }
    }

    Timer {
        interval: 1200
        running: player.metadataEditor !== null && player.metadataEditor.saveState === "saved"
        onTriggered: player.metadataEditor.finishSave()
    }

    Item {
        id: top
        width: parent.width
        height: 64

        Column {
            x: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            SectionLabel {
                text: "Playing from " + (player.playback.playingSourceKind === "playlist" ? "playlist" : "folder")
            }

            Text {
                text: player.playback.playingSourceTitle
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                font.weight: Font.DemiBold
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4

            IconButton {
                icon: "info"
                iconSize: 18
                tip: player.showTags ? "Hide editable tags" : "Edit track tags"
                visible: player.metadataEditor !== null
                onClicked: player.showTags = !player.showTags
            }

            IconButton {
                icon: "queue"
                iconSize: 18
                tip: "Queue and history"
                onClicked: {
                    player.workspace.setFullscreen(false)
                    player.workspace.showRightPanel("queue")
                }
            }

            IconButton {
                objectName: "exitFullscreen"
                icon: "exit-fullscreen"
                iconSize: 18
                tip: "Exit fullscreen (Esc)"
                onClicked: player.workspace.setFullscreen(false)
            }
        }
    }

    Rectangle {
        id: tagEditor
        objectName: "fullscreenMetadataEditor"
        visible: player.showTags && player.metadataEditor !== null && player.playback.playingId.length > 0
        anchors.top: top.bottom
        anchors.bottom: bottom.top
        anchors.right: parent.right
        width: Math.min(340, parent.width * 0.42)
        color: Theme.sidebar

        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: 1
            color: Theme.separator
        }

        Flickable {
            id: tagScroller
            anchors.fill: parent
            anchors.margins: 16
            contentHeight: tagColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ThinScrollBar {}

            Column {
                id: tagColumn
                width: tagScroller.width
                spacing: 12

                SectionLabel { text: "Track tags" }

                Text {
                    width: tagColumn.width
                    text: {
                        const operations = player.recoveryForPlayingTrack()
                        if (!operations || operations.length === 0)
                            return ""

                        const inspectionFailed = operations.some(function(operation) {
                            return operation && operation.situation === "inspection_failed"
                        })
                        if (inspectionFailed)
                            return "MTEE could not inspect a previous tag save. Review its recovery files before editing."

                        const recovery = operations[0]
                        if (!recovery)
                            return ""
                        const fileName = recovery.fileName || "this track"
                        return "A previous tag save for " + fileName
                            + " needs recovery. Its source and recovery files were kept."
                    }
                    visible: text.length > 0
                    color: Theme.danger
                    wrapMode: Text.WordWrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Repeater {
                    id: tagFields
                    model: []

                    delegate: FieldEditor {
                        required property var modelData
                        width: tagColumn.width
                        label: modelData.label
                        value: modelData.value
                        mixed: modelData.mixed
                        editable: modelData.editable
                        reason: modelData.reason
                        onEditingStarted: player.metadataEditor.beginTrackFieldEdit(
                            player.playback.playingId, modelData.key)
                        onCommitted: (value, remove) => player.metadataEditor.commitTrackField(
                            player.playback.playingId, modelData.key, value, remove)
                    }
                }

                Text {
                    width: tagColumn.width
                    visible: player.metadataEditor.saveState !== "idle"
                    text: player.metadataEditor.saveState === "saving" ? "Saving…"
                        : player.metadataEditor.saveState === "saved" ? "Saved"
                        : player.metadataEditor.saveMessage || "Could not save"
                    color: player.metadataEditor.saveState === "error"
                        || player.metadataEditor.saveState === "recovery" ? Theme.danger : Theme.textSecondary
                    wrapMode: Text.WordWrap
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSmall
                }

                Row {
                    spacing: 8

                    TextButton {
                        visible: player.metadataEditor.saveState === "error"
                            || player.metadataEditor.saveState === "busy"
                        kind: "neutral"
                        text: "Retry"
                        onClicked: player.metadataEditor.retrySave()
                    }

                    TextButton {
                        visible: player.metadataEditor.saveState === "busy"
                            && player.metadataEditor.canStopPlaybackAndSave
                        kind: "neutral"
                        text: "Stop playback and save"
                        onClicked: player.metadataEditor.stopPlaybackAndSave()
                    }

                    TextButton {
                        visible: player.metadataEditor.canUndo
                        kind: "ghost"
                        text: "Undo"
                        onClicked: player.metadataEditor.undoSave()
                    }
                }
            }
        }

        function refreshFields() {
            if (player.showTags && player.metadataEditor !== null && player.playback.playingId.length > 0)
                tagFields.model = player.metadataEditor.fieldsForTrack(player.playback.playingId)
            else
                tagFields.model = []
        }

        Connections {
            target: player.metadataEditor
            function onChanged() { tagEditor.refreshFields() }
        }

        Connections {
            target: player.playback
            function onPlaybackChanged() { player.refreshTagFields() }
        }

        Component.onCompleted: refreshFields()
    }

    Column {
        id: stage
        anchors.top: top.bottom
        anchors.bottom: bottom.top
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 96, 960)

        readonly property int coverSize: Math.max(120, Math.min(380, height - 150))

        topPadding: Math.max(0, (height - coverSize - 110) / 2)
        spacing: 18

        CoverArt {
            objectName: "fullscreenPlayerCover"
            anchors.horizontalCenter: parent.horizontalCenter
            width: stage.coverSize
            height: stage.coverSize
            pattern: player.track.cover !== undefined ? player.track.cover : -1
            source: player.track.coverUrl || ""
        }

        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            spacing: 6

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: player.track.title || ""
                elide: Text.ElideRight
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: 32
                font.weight: Font.Bold
            }

            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: player.track.artist && player.track.artist.length > 0 ? player.track.artist : "Unknown artist"
                elide: Text.ElideRight
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 16
            }
        }
    }

    Column {
        id: bottom
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 32
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(parent.width - 96, 960)
        spacing: 12

        WaveformView {
            objectName: "waveformView"
            waveform: player.waveform
            playback: player.playback
            width: parent.width
            height: Theme.waveHeight
            visible: player.waveform.state === "ready"
        }

        Row {
            visible: player.waveform.state === "generating" || player.waveform.state === "unavailable"
            width: parent.width
            height: 40
            spacing: 10

            Text {
                width: parent.width - retryWaveform.width - parent.spacing
                height: parent.height
                verticalAlignment: Text.AlignVCenter
                text: player.waveform.state === "generating"
                    ? "Generating waveform · " + Math.round(player.waveform.progress * 100) + "%"
                    : player.waveform.error || "Waveform unavailable"
                color: player.waveform.state === "unavailable" ? Theme.textSecondary : Theme.textMuted
                elide: Text.ElideRight
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            TextButton {
                id: retryWaveform
                visible: player.waveform.state === "unavailable"
                kind: "ghost"
                text: "Retry"
                onClicked: player.waveform.retry()
            }
        }

        Row {
            visible: player.playback.status === "Error"
            width: parent.width
            spacing: 8

            Text {
                width: parent.width - retryButton.width - nextButton.width - 16
                text: player.playback.errorMessage || "Playback failed."
                elide: Text.ElideRight
                color: Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeBody
                anchors.verticalCenter: parent.verticalCenter
            }

            IconButton {
                id: retryButton
                width: 32
                height: 30
                icon: "play"
                iconSize: 16
                tip: "Retry"
                onClicked: player.playback.retry()
            }

            IconButton {
                id: nextButton
                width: 32
                height: 30
                icon: "next"
                iconSize: 16
                tip: "Next"
                onClicked: player.playback.next()
            }
        }

        Item {
            width: parent.width
            height: 56

            TransportControls {
                anchors.centerIn: parent
                player: player.playback
                spacing: 20
                buttonSize: 40
                iconSize: 22
                playSize: 56
            }

            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                IconButton {
                    anchors.verticalCenter: parent.verticalCenter
                    hoverBackground: false
                    icon: player.playback.muted || player.playback.volume === 0 ? "volume-off" : "volume"
                    iconSize: 20
                    tip: player.playback.muted ? "Unmute" : "Mute"
                    onClicked: player.playback.toggleMute()
                }

                LineSlider {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 110
                    from: 0
                    to: 100
                    value: player.playback.muted ? 0 : player.playback.volume
                    onMoved: (value) => player.playback.setVolume(Math.round(value))
                }
            }
        }
    }
}
