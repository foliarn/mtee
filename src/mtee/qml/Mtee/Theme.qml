pragma Singleton
import QtQuick

// Visual direction validated in PLAN.md section 3: dark interface, rounded
// panels, intermediate density. Colours and sizes live here only.
QtObject {
    readonly property color background: "#080E18"
    readonly property color panel: "#111B2B"
    readonly property color activeSurface: "#1B2A40"
    readonly property color textPrimary: "#EDF2FA"
    readonly property color textSecondary: "#A5B3C7"
    readonly property color accent: "#80B5FF"

    readonly property color border: Qt.rgba(0.51, 0.63, 0.78, 0.18)
    readonly property color hover: Qt.rgba(0.50, 0.71, 1.0, 0.08)
    readonly property color selection: Qt.rgba(0.50, 0.71, 1.0, 0.16)
    readonly property color danger: "#FF9A8B"

    // Python registers the embedded font and sets it as the application font.
    readonly property string fontFamily: Qt.application.font.family
    readonly property int fontSizeBody: 14
    readonly property int fontSizeSmall: 12
    readonly property int fontSizeTitle: 18

    readonly property int rowHeight: 36
    readonly property int panelRadius: 12
    readonly property int controlRadius: 7
    readonly property int spacingSmall: 6
    readonly property int spacing: 12
    readonly property int spacingLarge: 20

    readonly property int sidebarWidth: 240
    readonly property int detailsWidth: 300
    readonly property int playerHeight: 76
    readonly property int compactWidth: 1100
}
