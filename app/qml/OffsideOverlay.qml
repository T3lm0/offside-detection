import QtQuick
import QtQuick3D

// Lines of the selected play at the moment of the pass:
// - blue: offside line (second-last defender or ball) and its uncertainty band
// - red: attacker's most advanced valid part
// - points used to compute them, with their vertical projection on the grass
Node {
    id: overlay

    required property var info
    property real pitchWidth: 68
    property bool showUncertainty: true
    property bool showWalls: true

    readonly property bool valid: info.valid === true
    readonly property color defenderColor: "#2f8cff"
    readonly property color attackerColor: "#ff3b30"
    readonly property real wallHeight: 230
    readonly property real lineX: valid ? info.lineX : 0
    readonly property real attackerX: valid ? info.attackerX : 0
    readonly property color marginColor: valid && info.status === "offside" ? "#ff6b5f" : "#4cd964"

    visible: valid

    component FlatMaterial: PrincipledMaterial {
        lighting: PrincipledMaterial.NoLighting
        cullMode: Material.NoCulling
    }

    // Strip on the grass across the whole width of the pitch
    component GroundStrip: Model {
        id: strip
        property real stripWidth: 10
        property color color: "white"
        property real stripOpacity: 1
        property real height: 4
        source: "#Rectangle"
        y: strip.height
        eulerRotation.x: -90
        scale: Qt.vector3d(strip.stripWidth / 100, overlay.pitchWidth + 4, 1)
        castsShadows: false
        receivesShadows: false
        materials: FlatMaterial {
            baseColor: Qt.rgba(strip.color.r, strip.color.g, strip.color.b, strip.stripOpacity)
            alphaMode: strip.stripOpacity < 1 ? PrincipledMaterial.Blend : PrincipledMaterial.Opaque
        }
    }

    // Translucent vertical plane over the line
    component Wall: Model {
        id: wall
        property color color: "white"
        property real wallOpacity: 0.15
        source: "#Rectangle"
        y: overlay.wallHeight / 2
        eulerRotation.y: 90
        scale: Qt.vector3d(overlay.pitchWidth + 4, overlay.wallHeight / 100, 1)
        castsShadows: false
        receivesShadows: false
        materials: FlatMaterial {
            baseColor: Qt.rgba(wall.color.r, wall.color.g, wall.color.b, wall.wallOpacity)
            alphaMode: PrincipledMaterial.Blend
        }
    }

    // Body point used and its plumb line to the ground
    component KeyPoint: Node {
        id: key
        property vector3d point
        property color color: "white"
        Model {
            source: "#Sphere"
            position: key.point
            scale: Qt.vector3d(0.17, 0.17, 0.17)
            castsShadows: false
            materials: FlatMaterial { baseColor: key.color }
        }
        Model {
            source: "#Cylinder"
            position: Qt.vector3d(key.point.x, key.point.y / 2, key.point.z)
            scale: Qt.vector3d(0.025, Math.max(key.point.y, 1) / 100, 0.025)
            castsShadows: false
            materials: FlatMaterial { baseColor: key.color }
        }
        Model {
            source: "#Cylinder"
            position: Qt.vector3d(key.point.x, 5, key.point.z)
            scale: Qt.vector3d(0.3, 0.004, 0.3)
            castsShadows: false
            materials: FlatMaterial { baseColor: key.color }
        }
    }

    GroundStrip {
        visible: overlay.showUncertainty && overlay.valid && overlay.info.uncertainty > 0
        x: overlay.lineX
        height: 3
        stripWidth: overlay.valid ? 2 * overlay.info.uncertainty : 0
        color: overlay.defenderColor
        stripOpacity: 0.28
    }
    GroundStrip { x: overlay.lineX; stripWidth: 9; color: overlay.defenderColor }
    GroundStrip { x: overlay.attackerX; stripWidth: 9; color: overlay.attackerColor; height: 4.5 }

    Wall { visible: overlay.showWalls; x: overlay.lineX; color: overlay.defenderColor; wallOpacity: 0.16 }
    Wall { visible: overlay.showWalls; x: overlay.attackerX; color: overlay.attackerColor; wallOpacity: 0.11 }

    // Margin between the two lines at the attacker's position
    Model {
        visible: overlay.valid && overlay.info.attackerHasPoint
        source: "#Rectangle"
        position: Qt.vector3d((overlay.lineX + overlay.attackerX) / 2, 6,
                              overlay.valid ? overlay.info.attackerPoint.z : 0)
        eulerRotation.x: -90
        scale: Qt.vector3d(Math.abs(overlay.attackerX - overlay.lineX) / 100, 0.35, 1)
        castsShadows: false
        materials: FlatMaterial { baseColor: overlay.marginColor }
    }

    KeyPoint {
        visible: overlay.valid && overlay.info.attackerHasPoint
        point: overlay.valid ? overlay.info.attackerPoint : Qt.vector3d(0, 0, 0)
        color: overlay.attackerColor
    }
    KeyPoint {
        visible: overlay.valid && overlay.info.defenderHasPoint && !overlay.info.lineFromBall
        point: overlay.valid ? overlay.info.defenderPoint : Qt.vector3d(0, 0, 0)
        color: overlay.defenderColor
    }
}
