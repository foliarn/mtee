import QtQuick
import QtQuick.Controls.Basic
import Mtee

// The two modal dialogs of the Plugins view (plan 123.6): the warning before a plugin is installed
// and the refusal of an install. Both follow workspace.pluginsView, so they open from any view;
// Main.qml hosts this item once. Escape or a click outside counts as Cancel or Close.
Item {
    id: host

    required property var workspace
    readonly property var view: workspace.pluginsView
    readonly property var pending: view ? view.pendingInstall : ({})
    readonly property var refusal: view ? view.refusal : ({})
    readonly property bool hasPending: !!pending && Object.keys(pending).length > 0
    readonly property bool hasRefusal: !!refusal && Object.keys(refusal).length > 0

    objectName: "pluginInstallHost"

    Component.onCompleted: {
        if (hasPending) installPopup.open()
        if (hasRefusal) refusalPopup.open()
    }
    onHasPendingChanged: hasPending ? installPopup.open() : installPopup.close()
    onHasRefusalChanged: hasRefusal ? refusalPopup.open() : refusalPopup.close()

    Popup {
        id: installPopup
        objectName: "pluginInstallDialog"
        parent: Overlay.overlay
        width: Math.min(480, parent.width - 32)
        height: installColumn.implicitHeight + 40
        x: (parent.width - width) / 2
        y: Math.max(16, (parent.height - height) / 2)
        modal: true
        focus: true
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        onClosed: if (host.hasPending && host.view) host.view.cancelInstall()

        contentItem: Column {
            id: installColumn
            width: installPopup.availableWidth
            spacing: 14

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                text: "Install " + host.pending.title + " " + host.pending.version + "?"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeTitle
                font.weight: Font.DemiBold
            }

            Text {
                objectName: "pluginInstallSource"
                width: parent.width
                wrapMode: Text.WordWrap
                text: host.pending.sourceText || ""
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }

            // The facts of the package, as label and value pairs.
            Grid {
                width: parent.width
                columns: 2
                columnSpacing: 24
                rowSpacing: 8
                verticalItemAlignment: Grid.AlignVCenter

                Text { text: "Author"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { text: host.pending.author || ""; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }

                Text { text: "Version"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { text: host.pending.version || ""; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }

                Text { text: "Size"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text { text: host.pending.sizeText || ""; color: Theme.textPrimary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSecondary }

                Text { text: "Network"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Rectangle {
                    visible: host.pending.usesNetwork === true
                    width: networkText.implicitWidth + 12
                    height: 18
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.separator
                    radius: Theme.badgeRadius

                    Text {
                        id: networkText
                        anchors.centerIn: parent
                        text: "Uses the network"
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontSizeCaption
                    }
                }
                Text {
                    visible: host.pending.usesNetwork !== true
                    text: "No network"
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }

                Text { text: "Libraries"; color: Theme.textMuted; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
                Text {
                    text: host.pending.librariesCount ? host.pending.librariesCount + " bundled" : "None"
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeSecondary
                }
            }

            NoticeCard {
                objectName: "pluginInstallWarning"
                title: "A plugin runs with full access to this computer."
                text: "Install only plugins you trust."
            }

            Item {
                width: parent.width
                height: installButtons.implicitHeight

                Row {
                    id: installButtons
                    anchors.right: parent.right
                    spacing: 8

                    TextButton {
                        objectName: "pluginInstallCancel"
                        text: "Cancel"
                        kind: "ghost"
                        onClicked: host.view.cancelInstall()
                    }

                    TextButton {
                        objectName: "pluginInstallConfirm"
                        text: "Install"
                        kind: "primary"
                        onClicked: host.view.confirmInstall()
                    }
                }
            }
        }
    }

    Popup {
        id: refusalPopup
        objectName: "pluginRefusalDialog"
        parent: Overlay.overlay
        width: Math.min(480, parent.width - 32)
        height: refusalColumn.implicitHeight + 40
        x: (parent.width - width) / 2
        y: Math.max(16, (parent.height - height) / 2)
        modal: true
        focus: true
        padding: 20
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle { color: Theme.surface; border.color: Theme.separator; radius: 8 }
        onClosed: if (host.hasRefusal && host.view) host.view.dismissRefusal()

        contentItem: Column {
            id: refusalColumn
            width: refusalPopup.availableWidth
            spacing: 14

            Row {
                spacing: 8

                Icon {
                    anchors.verticalCenter: parent.verticalCenter
                    name: "alert"
                    size: 18
                    color: Theme.danger
                }

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: host.refusal.title || ""
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeTitle
                    font.weight: Font.DemiBold
                }
            }

            Text {
                objectName: "pluginRefusalText"
                width: parent.width
                wrapMode: Text.WordWrap
                text: host.refusal.text || ""
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSecondary
            }

            Item {
                width: parent.width
                height: refusalButtons.implicitHeight

                Row {
                    id: refusalButtons
                    anchors.right: parent.right

                    TextButton {
                        objectName: "pluginRefusalClose"
                        text: "Close"
                        kind: "primary"
                        onClicked: host.view.dismissRefusal()
                    }
                }
            }
        }
    }
}
