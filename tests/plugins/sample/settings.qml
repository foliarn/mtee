import QtQuick
import Mtee

// The Settings page of the sample plugin. It uses the rows of the Mtee module, so it looks like
// the pages of the core. ``workspace`` and ``backend`` are set by the core after loading, so
// every binding reads ``backend`` with a fallback.
Column {
    id: page

    property var workspace
    property var backend
    readonly property bool signedIn: backend ? backend.signedIn : false

    objectName: "sampleSettingsPage"
    spacing: 8

    Group { title: "Sample plugin" }

    FieldRow {
        objectName: "sampleLabel"
        label: "Label"
        description: "A text saved in the settings of the plugin."
        placeholder: "Type a label"
        value: page.backend ? page.backend.label : ""
        onEdited: (text) => page.backend.setLabel(text)
    }

    ToggleRow {
        objectName: "sampleLoud"
        label: "Loud mode"
        description: "A switch saved in the settings of the plugin."
        checked: page.backend ? page.backend.loud : false
        onToggled: (checked) => page.backend.setLoud(checked)
    }

    StepperRow {
        objectName: "sampleCopies"
        label: "Copies"
        description: "A number kept between 1 and 5."
        from: 1
        to: 5
        value: page.backend ? page.backend.copies : 1
        onChosen: (value) => page.backend.setCopies(value)
    }

    InfoRow {
        objectName: "sampleItems"
        label: "Rows in the plugin table"
        description: "Read from sample_items, which the plugin migration created."
        value: page.backend ? String(page.backend.itemCount) : ""
    }

    ActionRow {
        objectName: "sampleSignIn"
        label: "Account"
        description: page.signedIn ? "Signed in. Enter this code on the other device." : "Not signed in."
        detail: page.signedIn ? "The code works for five minutes." : ""
        code: page.signedIn ? "KQ4-7ZPM" : ""
        actionText: page.signedIn ? "Sign out" : "Sign in"
        actionKind: page.signedIn ? "ghost" : "primary"
        onAction: page.backend.toggleSignIn()
    }

    NoticeCard {
        objectName: "sampleNotice"
        visible: page.signedIn
        title: "The sample is limiting requests"
        text: "Nothing is sent anywhere: this card only shows how a notice looks."
    }
}
