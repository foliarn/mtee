import QtQuick
import QtQuick.Controls.Basic

Menu {
    id: menu

    padding: 4
    overlap: 4
    implicitWidth: 260

    delegate: AppMenuItem {}

    background: Rectangle {
        implicitWidth: 260
        color: Theme.surface
        border.width: 1
        border.color: Theme.separator
    }
}
