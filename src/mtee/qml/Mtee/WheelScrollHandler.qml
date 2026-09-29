import QtQuick

Item {
    id: handler

    required property Flickable flickable
    property real wheelTargetY: flickable.contentY

    WheelHandler {
        parent: handler.flickable
        target: null
        blocking: false

        onWheel: (event) => {
            if (event.modifiers & Qt.ShiftModifier)
                return
            if (event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0
                || event.angleDelta.x !== 0 || event.angleDelta.y === 0)
                return

            const lines = Application.styleHints.wheelScrollLines
            const pixelsPerNotch = lines > 0 ? lines * 24 : handler.flickable.height
            const distance = event.angleDelta.y / 120 * pixelsPerNotch * 1.25
            const minimum = handler.flickable.originY
            const maximum = Math.max(minimum, handler.flickable.originY
                + handler.flickable.contentHeight - handler.flickable.height)
            if (!wheelAnimation.running)
                handler.wheelTargetY = handler.flickable.contentY
            const target = Math.max(minimum, Math.min(maximum, handler.wheelTargetY - distance))
            if (target === handler.wheelTargetY)
                return
            handler.wheelTargetY = target
            wheelAnimation.stop()
            wheelAnimation.from = handler.flickable.contentY
            wheelAnimation.to = target
            wheelAnimation.start()
            event.accepted = true
        }
    }

    NumberAnimation {
        id: wheelAnimation
        target: handler.flickable
        property: "contentY"
        duration: 220
        easing.type: Easing.OutExpo
    }

    Connections {
        target: handler.flickable
        function onMovementStarted() {
            wheelAnimation.stop()
            handler.wheelTargetY = handler.flickable.contentY
        }
    }
}
