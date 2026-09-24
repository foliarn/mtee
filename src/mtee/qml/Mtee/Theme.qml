pragma Singleton
import QtQuick

// Visual direction of docs/ux/specification.md, revision 2: palette Acid,
// neutral dark greys, square corners, lime primary and magenta secondary.
// Colours and sizes live here only.
QtObject {
    // Surfaces, from the darkest chrome to the lightest selection.
    readonly property color chrome: "#0B0B0C"
    readonly property color sidebar: "#111113"
    readonly property color editor: "#18181B"
    readonly property color surface: "#212125"
    readonly property color selection: "#2A2A30"
    readonly property color separator: "#2E2E33"
    readonly property color background: editor

    readonly property color textPrimary: "#FFFFFF"
    readonly property color textSecondary: "#A1A1AA"
    readonly property color textMuted: "#6B6B73"
    readonly property color textOnColor: "#0A0A0A"

    readonly property color primary: "#C6FF1A"
    readonly property color primaryHover: "#D6FF5C"
    readonly property color secondary: "#FF2E88"
    readonly property color danger: "#FF4D4D"
    readonly property color closeHover: "#E81123"

    readonly property color hover: surface
    readonly property color focus: primary

    // Camelot wheel, one hue per number, independent from the palette.
    readonly property var camelotColors: [
        "#6FF2D0", "#8EF59B", "#C9EE8A", "#F3DD8A", "#F9B489", "#F99C9C",
        "#F59CC9", "#E39CF3", "#C0A5F7", "#A7B8F9", "#8FD1F8", "#79E7F2"
    ]

    function camelotColor(key) {
        const number = parseInt(key, 10)
        if (isNaN(number) || number < 1 || number > 12)
            return selection
        return camelotColors[number - 1]
    }

    // Python registers the embedded font and sets it as the application font.
    readonly property string fontFamily: Qt.application.font.family
    readonly property int fontSizeBody: 14
    readonly property int fontSizeSmall: 12
    readonly property int fontSizeSecondary: 13
    readonly property int fontSizeCaption: 11
    readonly property int fontSizeTitle: 18
    readonly property int fontSizeHeading: 28

    readonly property int radius: 0
    readonly property int badgeRadius: 2
    readonly property int spacingSmall: 6
    readonly property int spacing: 12
    readonly property int spacingLarge: 20

    readonly property int titleBarHeight: 32
    readonly property int windowButtonWidth: 46
    readonly property int activityBarWidth: 48
    readonly property int sidebarWidth: 240
    readonly property int rightPanelWidth: 320
    readonly property int tabHeight: 36
    readonly property int rowHeight: 56
    readonly property int coverSize: 40
    readonly property int islandHeight: 72
    readonly property int islandMargin: 16
    readonly property int islandMaxWidth: 960
    readonly property int treeRowHeight: 24

    // Width thresholds of the reduced layouts.
    readonly property int compactSidebarWidth: 1160
    readonly property int singleGroupWidth: 930
}
