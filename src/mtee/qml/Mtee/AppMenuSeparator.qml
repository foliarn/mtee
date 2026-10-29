import QtQuick
import QtQuick.Controls.Basic

MenuSeparator {
    // A hidden separator takes no room (see AppMenuItem).
    height: visible ? implicitHeight : 0
    padding: 0
    topPadding: 4
    bottomPadding: 4

    contentItem: Rectangle {
        implicitWidth: 240
        implicitHeight: 1
        color: Theme.separator
    }
}
