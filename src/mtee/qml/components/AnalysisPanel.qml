import QtQuick
import QtQuick.Controls.Basic
import Mtee

Rectangle {
    id: panel

    required property var analysisModel
    property string trackId: ""
    property bool analyzeOnlyTrack: false

    objectName: "analysisPanel"
    color: Theme.sidebar

    onTrackIdChanged: {
        if (analysisModel !== null)
            analysisModel.setTrackId(trackId)
    }
    Component.onCompleted: {
        if (analysisModel !== null)
            analysisModel.setTrackId(trackId)
    }

    Column {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        Row {
            width: parent.width
            spacing: 8

            Text {
                width: parent.width - runButton.width - parent.spacing
                text: "Audio analysis"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSection
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            TextButton {
                id: runButton
                kind: "neutral"
                text: panel.analysisModel.isRunning ? "Analyzing…"
                    : panel.analyzeOnlyTrack ? "Analyze track" : "Analyze selected"
                enabled: !panel.analysisModel.isRunning
                onClicked: panel.analyzeOnlyTrack
                    ? panel.analysisModel.analyzeTrack(panel.trackId)
                    : panel.analysisModel.analyzeSelected()
            }
        }

        Text {
            width: parent.width
            text: panel.trackId.length ? panel.trackId : "Select or play a track to see its analysis."
            color: Theme.textMuted
            elide: Text.ElideMiddle
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Row {
            visible: panel.analysisModel.isRunning
            width: parent.width
            spacing: 8
            ProgressBar {
                width: parent.width - cancelButton.width - parent.spacing
                value: panel.analysisModel.progress
            }
            TextButton { id: cancelButton; kind: "ghost"; text: "Cancel"; onClicked: panel.analysisModel.cancel() }
        }

        Text {
            width: parent.width
            visible: panel.analysisModel.error.length > 0
            text: panel.analysisModel.error
            color: Theme.danger
            wrapMode: Text.WordWrap
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Flickable {
            width: parent.width
            height: Math.max(0, parent.height - y)
            contentHeight: resultsColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: resultsColumn
                width: parent.width
                spacing: 14

                Repeater {
                    model: panel.analysisModel.results
                    delegate: Column {
                        required property var modelData
                        width: resultsColumn.width
                        spacing: 5

                        Text {
                            text: modelData.analyzer.charAt(0).toUpperCase()
                                + modelData.analyzer.slice(1) + " · " + modelData.status
                                + (modelData.source_stale ? " · Source changed" : "")
                            color: modelData.status === "failed" || modelData.status === "stale"
                                ? Theme.danger : Theme.textPrimary
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeBody
                            font.weight: Font.DemiBold
                        }

                        Repeater {
                            model: modelData.metrics
                            delegate: Text {
                                required property var modelData
                                width: resultsColumn.width
                                text: modelData.name.replaceAll("_", " ") + ": "
                                    + (modelData.value === null ? "Not available" : modelData.value)
                                    + (modelData.unit.length ? " " + modelData.unit : "")
                                color: Theme.textSecondary
                                wrapMode: Text.WordWrap
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontSizeSmall
                            }
                        }

                        Text {
                            visible: modelData.diagnostics.length > 0
                            text: modelData.diagnostics
                            color: Theme.textMuted
                            wrapMode: Text.WordWrap
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.fontSizeSmall
                        }
                    }
                }
            }
        }

        Text {
            visible: panel.analysisModel.overrides.length > 0
            text: "Manual confirmations"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
        }
        Repeater {
            model: panel.analysisModel.overrides
            delegate: Text {
                required property var modelData
                width: parent.width
                text: modelData.field_name + ": " + modelData.value
                    + (modelData.source_stale ? " · Source changed" : "")
                    + (modelData.active ? " · Active" : " · Previous")
                color: modelData.source_stale ? Theme.danger : Theme.textSecondary
                wrapMode: Text.WordWrap
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
        }

        Text { text: "Confirm calculated value"; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; font.weight: Font.DemiBold }
        Row {
            width: parent.width
            spacing: 6
            TextField { id: bpmValue; width: (parent.width - 6) / 2; placeholderText: "BPM"; text: panel.calculated("tempo_bpm"); selectByMouse: true }
            TextButton { kind: "neutral"; text: "Confirm"; onClicked: panel.analysisModel.confirm("tempo_bpm", bpmValue.text) }
        }
        Row {
            width: parent.width
            spacing: 6
            TextButton { kind: "ghost"; text: "Half tempo"; onClicked: panel.analysisModel.confirmHalfTempo() }
            TextButton { kind: "ghost"; text: "Double tempo"; onClicked: panel.analysisModel.confirmDoubleTempo() }
            TextButton { kind: "ghost"; text: "Use calculated"; onClicked: panel.analysisModel.useCalculatedValue("tempo_bpm") }
        }
        Row {
            width: parent.width
            spacing: 6
            TextField { id: keyValue; width: (parent.width - 6) / 2; placeholderText: "Key"; text: panel.calculated("key"); selectByMouse: true }
            TextButton { kind: "neutral"; text: "Confirm"; onClicked: panel.analysisModel.confirm("key", keyValue.text) }
            TextButton { kind: "ghost"; text: "Use calculated"; onClicked: panel.analysisModel.useCalculatedValue("key") }
        }
    }

    function calculated(fieldName) {
        if (analysisModel === null)
            return ""
        const value = analysisModel.calculatedValue(fieldName)
        return value === null || value === undefined ? "" : String(value)
    }
}
