import QtQuick
import QtQuick.Controls.Basic

Menu {
    id: menu

    padding: 4
    overlap: 4
    implicitWidth: 260

    // Modal and not dimmed, like Popover (fix 137): a press outside closes the menu and is consumed,
    // so the click on the button that opened it cannot reach that button and reopen the menu.
    modal: true
    dim: false
    Overlay.modal: Item {}

    delegate: AppMenuItem {}

    background: Rectangle {
        implicitWidth: 260
        color: Theme.surface
        border.width: 1
        border.color: Theme.separator
        radius: Theme.radius
    }
}
