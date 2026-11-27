import QtQuick
import QtQuick3D

// Shirt numbers above each player's head, drawn in 2D over the 3D view.
Item {
    id: root

    required property View3D view
    required property var labels
    property real tagScale: 1

    Repeater {
        // Repeated by label count so delegates are reused between frames
        model: root.labels.length
        delegate: Item {
            id: label
            required property int index
            readonly property var entry: root.labels[index]
            // Depends on the camera's actual transform, which updates after its properties
            readonly property vector3d screen: {
                const camera = root.view.camera
                if (!entry || !camera)
                    return Qt.vector3d(0, 0, -1)
                camera.scenePosition; camera.sceneRotation; root.view.width; root.view.height
                return root.view.mapFrom3DScene(entry.position)
            }
            visible: entry !== undefined && screen.z > 0
            x: Math.round(screen.x - width / 2)
            y: Math.round(screen.y - height)
            width: tag.width
            height: tag.height
            z: entry && entry.key ? 2 : 1
            // Grows upwards from the head
            scale: root.tagScale
            transformOrigin: Item.Bottom

            Rectangle {
                id: tag
                width: text.implicitWidth + 10
                height: text.implicitHeight + 4
                radius: 4
                color: Qt.rgba(0.05, 0.07, 0.09, label.entry && label.entry.approximate ? 0.5 : 0.8)
                border.color: label.entry ? label.entry.color : "white"
                border.width: label.entry && label.entry.key ? 2 : 1

                Text {
                    id: text
                    anchors.centerIn: parent
                    text: label.entry ? label.entry.text + (label.entry.approximate ? " ~" : "") : ""
                    color: "white"
                    font.pixelSize: label.entry && label.entry.key ? 13 : 11
                    font.bold: label.entry && label.entry.key
                }
            }
        }
    }
}
