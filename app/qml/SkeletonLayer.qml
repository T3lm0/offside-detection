import QtQuick
import QtQuick3D
import OffsideViewer

// Every skeleton in the scene. Each part is a single Model instanced from C++.
Node {
    id: layer

    required property SceneController controller
    property bool showLowConfidence: true
    property bool showShadows: true

    PrincipledMaterial { id: solidMaterial; baseColor: "white"; roughness: 0.5; metalness: 0.0 }
    PrincipledMaterial {
        id: translucentMaterial
        baseColor: "white"
        roughness: 0.6
        alphaMode: PrincipledMaterial.Blend
    }
    PrincipledMaterial {
        id: shadowMaterial
        baseColor: "black"
        lighting: PrincipledMaterial.NoLighting
        alphaMode: PrincipledMaterial.Blend
    }

    // Enough confidence
    Model {
        source: "#Cylinder"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Bones }
        materials: solidMaterial
        castsShadows: true
    }
    Model {
        source: "#Sphere"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Joints }
        materials: solidMaterial
        castsShadows: true
    }
    Model {
        source: "#Sphere"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Heads }
        materials: solidMaterial
        castsShadows: true
    }

    // Low confidence: translucent
    Model {
        visible: layer.showLowConfidence
        source: "#Cylinder"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Bones; lowConfidence: true }
        materials: translucentMaterial
        castsShadows: false
    }
    Model {
        visible: layer.showLowConfidence
        source: "#Sphere"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Joints; lowConfidence: true }
        materials: translucentMaterial
        castsShadows: false
    }
    Model {
        visible: layer.showLowConfidence
        source: "#Sphere"
        instancing: SkeletonInstancing { controller: layer.controller; part: SkeletonInstancing.Heads; lowConfidence: true }
        materials: translucentMaterial
        castsShadows: false
    }

    // Players whose only known data is their ground position (no pose)
    Model {
        source: "#Cylinder"
        instancing: SkeletonInstancing {
            controller: layer.controller
            part: SkeletonInstancing.GroundMarkers
            hasTransparency: true
        }
        materials: translucentMaterial
        castsShadows: false
    }

    // Contact shadows: they help see where each player stands from any angle
    Model {
        visible: layer.showShadows
        source: "#Sphere"
        instancing: SkeletonInstancing {
            controller: layer.controller
            part: SkeletonInstancing.Shadows
            hasTransparency: true
        }
        materials: shadowMaterial
        castsShadows: false
        receivesShadows: false
    }
}
