import QtQuick
import Mtee

// Rounded surface used for every named zone of the window. Children are laid
// out by the caller, so the component keeps no default property alias.
Rectangle {
    color: Theme.panel
    radius: Theme.panelRadius
    border.width: 1
    border.color: Theme.border
}
