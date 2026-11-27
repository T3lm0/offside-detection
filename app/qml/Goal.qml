import QtQuick
import QtQuick3D

// Regulation goal (7.32 x 2.44 m) with net. direction = +1 if the net points towards +X.
Node {
    id: goal

    property int direction: 1
    readonly property real halfWidth: 366
    readonly property real goalHeight: 244
    readonly property real depth: 200
    readonly property real postScale: 0.12 // 12 cm diameter

    component NetPlane: Model {
        id: plane
        property real tilesU: 10
        property real tilesV: 10
        source: "#Rectangle"
        castsShadows: false
        materials: PrincipledMaterial {
            lighting: PrincipledMaterial.NoLighting
            cullMode: Material.NoCulling
            alphaMode: PrincipledMaterial.Mask
            alphaCutoff: 0.4
            baseColor: "#dfe4e6"
            baseColorMap: Texture {
                tilingModeHorizontal: Texture.Repeat
                tilingModeVertical: Texture.Repeat
                scaleU: plane.tilesU
                scaleV: plane.tilesV
                sourceItem: Rectangle {
                    width: 32
                    height: 32
                    color: "transparent"
                    border.color: "white"
                    border.width: 2
                }
            }
        }
    }

    PrincipledMaterial { id: postMaterial; baseColor: "#fafafa"; roughness: 0.3 }

    Model {
        source: "#Cylinder"
        position: Qt.vector3d(0, goal.goalHeight / 2, -goal.halfWidth)
        scale: Qt.vector3d(goal.postScale, goal.goalHeight / 100, goal.postScale)
        materials: postMaterial
    }
    Model {
        source: "#Cylinder"
        position: Qt.vector3d(0, goal.goalHeight / 2, goal.halfWidth)
        scale: Qt.vector3d(goal.postScale, goal.goalHeight / 100, goal.postScale)
        materials: postMaterial
    }
    Model {
        source: "#Cylinder"
        position: Qt.vector3d(0, goal.goalHeight, 0)
        eulerRotation.x: 90
        scale: Qt.vector3d(goal.postScale, (2 * goal.halfWidth + 12) / 100, goal.postScale)
        materials: postMaterial
    }

    // Net: back, roof and sides (~12 cm mesh)
    NetPlane {
        position: Qt.vector3d(goal.direction * goal.depth, goal.goalHeight / 2, 0)
        eulerRotation.y: 90
        scale: Qt.vector3d(2 * goal.halfWidth / 100, goal.goalHeight / 100, 1)
        tilesU: 61
        tilesV: 20
    }
    NetPlane {
        position: Qt.vector3d(goal.direction * goal.depth / 2, goal.goalHeight, 0)
        eulerRotation.x: -90
        scale: Qt.vector3d(goal.depth / 100, 2 * goal.halfWidth / 100, 1)
        tilesU: 17
        tilesV: 61
    }
    NetPlane {
        position: Qt.vector3d(goal.direction * goal.depth / 2, goal.goalHeight / 2, -goal.halfWidth)
        scale: Qt.vector3d(goal.depth / 100, goal.goalHeight / 100, 1)
        tilesU: 17
        tilesV: 20
    }
    NetPlane {
        position: Qt.vector3d(goal.direction * goal.depth / 2, goal.goalHeight / 2, goal.halfWidth)
        scale: Qt.vector3d(goal.depth / 100, goal.goalHeight / 100, 1)
        tilesU: 17
        tilesV: 20
    }
}
