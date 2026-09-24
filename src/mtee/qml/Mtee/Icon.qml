import QtQuick
import QtQuick.Window

// Tinted SVG icon from resources/icons, rendered by the Python icon provider.
Image {
    id: icon

    property string name: ""
    property color color: Theme.textSecondary
    property int size: 20

    function hex(value) {
        const text = value.toString()
        return text.length > 1 ? text.substring(1) : "ffffff"
    }

    width: size
    height: size
    source: name.length > 0 ? "image://icon/" + name + "/" + hex(color) : ""
    sourceSize: Qt.size(Math.ceil(size * Screen.devicePixelRatio), Math.ceil(size * Screen.devicePixelRatio))
    fillMode: Image.PreserveAspectFit
    smooth: true
}
