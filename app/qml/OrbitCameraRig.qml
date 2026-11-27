import QtQuick
import QtQuick3D

// Orbit camera: rotates around "target" with yaw (vertical axis) and pitch (tilt).
// Scene units: 1 = 1 cm.
Node {
    id: rig

    property real yaw: 0
    property real pitch: -30
    property real distance: 9000
    property vector3d target: Qt.vector3d(0, 0, 0)
    property real fieldOfView: 38
    // With Horizontal the visible width does not depend on the aspect ratio: portrait gains pitch above and below
    property int fieldOfViewOrientation: PerspectiveCamera.Vertical
    property bool instant: false
    readonly property alias camera: camera
    readonly property bool animating: transition.running

    position: target

    Node {
        eulerRotation.y: rig.yaw
        Node {
            eulerRotation.x: rig.pitch
            PerspectiveCamera {
                id: camera
                z: rig.distance
                clipNear: 20
                clipFar: 22000
                fieldOfView: rig.fieldOfView
                fieldOfViewOrientation: rig.fieldOfViewOrientation
            }
        }
    }

    function orbitBy(dx, dy) {
        transition.stop()
        yaw -= dx * 0.3
        pitch = Math.max(-89.5, Math.min(-1, pitch - dy * 0.3))
    }

    function panBy(dx, dy) {
        transition.stop()
        const k = distance * 0.0011
        const r = yaw * Math.PI / 180
        // Ground axes as seen from the camera
        const right = Qt.vector3d(Math.cos(r), 0, -Math.sin(r))
        const forward = Qt.vector3d(-Math.sin(r), 0, -Math.cos(r))
        target = target.minus(right.times(dx * k)).plus(forward.times(dy * k))
    }

    function zoomBy(steps) {
        transition.stop()
        distance = Math.max(200, Math.min(30000, distance * Math.pow(0.87, steps)))
    }

    function moveTo(newTarget, newYaw, newPitch, newDistance) {
        // Rotate along the shortest path
        const toYaw = yaw + ((newYaw - yaw) % 360 + 540) % 360 - 180
        if (instant) {
            transition.stop()
            target = newTarget
            yaw = toYaw
            pitch = newPitch
            distance = newDistance
            return
        }
        targetAnimation.to = newTarget
        yawAnimation.to = toYaw
        pitchAnimation.to = newPitch
        distanceAnimation.to = newDistance
        transition.restart()
    }

    ParallelAnimation {
        id: transition
        Vector3dAnimation { id: targetAnimation; target: rig; property: "target"; duration: 900; easing.type: Easing.InOutCubic }
        NumberAnimation { id: yawAnimation; target: rig; property: "yaw"; duration: 900; easing.type: Easing.InOutCubic }
        NumberAnimation { id: pitchAnimation; target: rig; property: "pitch"; duration: 900; easing.type: Easing.InOutCubic }
        NumberAnimation { id: distanceAnimation; target: rig; property: "distance"; duration: 900; easing.type: Easing.InOutCubic }
    }
}
