import QtQuick
import QtQuick3D
import OffsideViewer

// Regulation pitch: striped grass, markings, goals and corner flags.
Node {
    id: pitch

    property real pitchLength: 105
    property real pitchWidth: 68
    readonly property int stripes: 18

    // Ground around the pitch
    Model {
        source: "#Rectangle"
        y: -3
        eulerRotation.x: -90
        scale: Qt.vector3d(pitch.pitchLength + 26, pitch.pitchWidth + 20, 1)
        receivesShadows: true
        materials: PrincipledMaterial { baseColor: "#1d4427"; roughness: 0.95 }
    }

    // Mowing stripes parallel to the goal line: they help read depth along the pitch
    Repeater3D {
        model: pitch.stripes
        delegate: Model {
            required property int index
            source: "#Rectangle"
            eulerRotation.x: -90
            x: (-pitch.pitchLength / 2 + (index + 0.5) * pitch.pitchLength / pitch.stripes) * 100
            scale: Qt.vector3d(pitch.pitchLength / pitch.stripes, pitch.pitchWidth + 6, 1)
            receivesShadows: true
            materials: PrincipledMaterial {
                baseColor: index % 2 ? "#2f7d40" : "#286d37"
                roughness: 0.92
            }
        }
    }

    Model {
        geometry: PitchLinesGeometry {
            pitchLength: pitch.pitchLength
            pitchWidth: pitch.pitchWidth
            lineWidth: 0.12
        }
        receivesShadows: true
        materials: PrincipledMaterial { baseColor: "#eef3ee"; roughness: 0.7; cullMode: Material.NoCulling }
    }

    // Stepped stands around the ground, only as a visual reference
    Repeater3D {
        model: 12
        delegate: Model {
            required property int index
            readonly property int side: index % 4 // 0/1: sides, 2/3: ends
            readonly property int tier: Math.floor(index / 4)
            readonly property real sign: side % 2 ? 1 : -1
            readonly property bool alongX: side < 2
            readonly property real offset: (alongX ? pitch.pitchWidth + 20 : pitch.pitchLength + 26) / 2 + 5 + tier * 10
            readonly property real tierHeight: 4 + tier * 5
            readonly property real span: (alongX ? pitch.pitchLength + 26 : pitch.pitchWidth + 20) + 40 + tier * 20
            source: "#Cube"
            position: alongX ? Qt.vector3d(0, tierHeight * 50, sign * offset * 100)
                             : Qt.vector3d(sign * offset * 100, tierHeight * 50, 0)
            scale: alongX ? Qt.vector3d(span, tierHeight, 10) : Qt.vector3d(10, tierHeight, span)
            castsShadows: false
            materials: PrincipledMaterial { baseColor: tier % 2 ? "#273038" : "#222a31"; roughness: 0.95 }
        }
    }

    Goal { x: pitch.pitchLength * 50; direction: 1 }
    Goal { x: -pitch.pitchLength * 50; direction: -1 }

    // Corner flags
    Repeater3D {
        model: 4
        delegate: Node {
            required property int index
            x: (index % 2 ? 1 : -1) * pitch.pitchLength * 50
            z: (index < 2 ? 1 : -1) * pitch.pitchWidth * 50
            Model {
                source: "#Cylinder"
                y: 75
                scale: Qt.vector3d(0.03, 1.5, 0.03)
                materials: PrincipledMaterial { baseColor: "#f2f2f2" }
            }
            Model {
                source: "#Rectangle"
                position: Qt.vector3d(0, 135, 20)
                eulerRotation.y: 90
                scale: Qt.vector3d(0.4, 0.3, 1)
                materials: PrincipledMaterial { baseColor: "#ffbe0b"; cullMode: Material.NoCulling }
            }
        }
    }
}
