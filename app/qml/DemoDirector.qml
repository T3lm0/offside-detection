import QtQuick
import OffsideViewer

// Scripted demo video: on every frame it places the camera, advances the play, sets layers and
// captions and records the window with FrameRecorder. Meant for the synthetic plays
// (jugada_sintetica*.json); started with --demo output.mp4.
Item {
    id: director

    required property SceneController scene
    required property var rig
    required property var layerFlags
    required property var host
    required property Item stage
    required property bool portrait
    required property string output
    required property url firstSource

    readonly property int fps: 30
    property int frame: 0
    property int shotIndex: -1
    property real shotStart: 0
    property var startCam: null
    property var lastCam: null
    property vector3d follow: Qt.vector3d(0, 0, 0)

    property string caption: ""
    property real captionOpacity: 0
    property string titleText: ""
    property string subtitleText: ""
    property real titleOpacity: 0
    property real blackOpacity: 0

    FrameRecorder {
        id: recorder
        window: director.host
    }

    function sibling(name) {
        return director.firstSource.toString().replace(/[^/]*$/, name)
    }
    function ease(u) {
        u = Math.max(0, Math.min(1, u))
        return u * u * (3 - 2 * u)
    }
    function mix(a, b, u) {
        return a + (b - a) * u
    }
    function cam(target, yaw, pitch, distance) {
        return { target: target, yaw: yaw, pitch: pitch, distance: distance }
    }
    function blend(a, b, u) {
        if (!a)
            return b
        return cam(Qt.vector3d(mix(a.target.x, b.target.x, u), mix(a.target.y, b.target.y, u), mix(a.target.z, b.target.z, u)),
                   mix(a.yaw, b.yaw, u), mix(a.pitch, b.pitch, u), mix(a.distance, b.distance, u))
    }
    // Blend in from the previous shot's camera during the first `seconds` of the shot
    function enter(local, seconds, b) {
        return blend(director.startCam, b, ease(local / seconds))
    }
    function info() {
        return director.scene.eventInfo
    }
    function focusPoint() {
        const a = info().attackerPoint, d = info().defenderPoint
        return Qt.vector3d((a.x + d.x) / 2, 90, (a.z + d.z) / 2)
    }
    function fade(local, dur) {
        return Math.min(1, local / 0.4, (dur - local) / 0.4)
    }

    // Script: each shot lasts `dur` seconds. position(u) gives the play frame and camera(u, local) the
    // camera; u goes from 0 to 1 along the shot.
    readonly property var shots: [
        { // Title over a descending aerial view
            dur: 4, lines: false, walls: false, labels: false, badge: false,
            title: "Detección de fuera de juego",
            subtitle: "Visión Artificial  ·  reconstrucción 3D",
            position: u => 0,
            camera: (u, l) => cam(Qt.vector3d(1500, 0, 0), mix(-35, -12, ease(u)), mix(-62, -36, ease(u)), mix(14000, 8800, ease(u)))
        },
        { // The play running, following the ball
            dur: 8, lines: false, walls: false, labels: true, badge: false,
            caption: "22 jugadores y 3 árbitros reconstruidos en 3D",
            position: u => mix(10, 100, u),
            camera: (u, l) => enter(l, 2.5, cam(Qt.vector3d(director.follow.x, 0, director.follow.z + 300),
                                                mix(-10, 12, u), mix(-26, -22, u), mix(5200, 4300, u)))
        },
        { // Slow motion up to the pass
            dur: 6, lines: false, walls: false, labels: true, badge: false,
            position: u => mix(100, 120, 1 - (1 - u) * (1 - u)),
            camera: (u, l) => blend(director.startCam, cam(director.focusPoint(), -25, -14, 2200), ease(u))
        },
        { // VAR view: the lines and the verdict appear
            dur: 8, lines: true, walls: true, labels: true, badge: true,
            caption: "Vista VAR: penúltimo defensor (azul) frente a atacante (rojo)",
            position: u => 120,
            camera: (u, l) => enter(l, 3.2, cam(Qt.vector3d(director.info().lineX, 120, director.focusPoint().z),
                                                0, -12, mix(3800, 2900, ease((l - 3.2) / 4.8))))
        },
        { // Orbit around the two points that decide
            dur: 10, lines: true, walls: false, labels: true, badge: true,
            caption: "Atacante: hombro derecho  ·  Defensor: talón",
            position: u => 120,
            camera: (u, l) => enter(l, 1.5, cam(director.focusPoint(), mix(-70, 70, ease(u)), mix(-9, -18, u), mix(980, 820, u)))
        },
        { // The play continues with the ball trail
            dur: 8, lines: true, walls: false, labels: true, badge: true,
            position: u => mix(120, 185, u),
            camera: (u, l) => enter(l, 2.0, cam(Qt.vector3d(director.follow.x, 0, director.follow.z),
                                                mix(-70, -95, u), -19, mix(2700, 2100, u)))
        },
        { // Tight variant: not conclusive
            dur: 5, source: "jugada_sintetica_ajustada.json", lines: true, walls: true, labels: true, badge: true,
            caption: "Margen +5 cm, menor que el umbral por la calidad de los datos: no concluyente",
            position: u => 120,
            camera: (u, l) => cam(Qt.vector3d(director.info().lineX, 120, director.focusPoint().z), mix(-6, 4, u), -12, mix(4300, 3500, ease(u)))
        },
        { // Onside variant
            dur: 5, source: "jugada_sintetica_legal.json", lines: true, walls: false, labels: true, badge: true,
            caption: "Margen −15 cm: posición legal",
            position: u => 120,
            camera: (u, l) => cam(director.focusPoint(), mix(-45, -15, u), -12, mix(1100, 900, ease(u)))
        },
        { // Closing
            dur: 4, lines: false, walls: false, labels: false, badge: false,
            title: "Alguien me hace un 3D de algun jugador asi wapo??",
            subtitle: "YOLO + ByteTrack  ·  pose 2D → 3D  ·  calibración de cámara  ·  Regla 11 (Fuera de juego)\nVisor 3D en C++ / Qt 3D",
            subtitlePortrait: "YOLO + ByteTrack  ·  pose 2D → 3D\ncalibración de cámara  ·  Regla 11\n\nVisor 3D en C++ / Qt Quick 3D",
            position: u => 120,
            camera: (u, l) => enter(l, 1.0, cam(Qt.vector3d(2500, 0, 0), mix(-20, -5, u), mix(-30, -55, ease(u)), mix(6000, 11000, ease(u))))
        }
    ]
    readonly property real total: shots.reduce((s, x) => s + x.dur, 0)

    function beginShot(index, start) {
        const s = shots[index]
        director.shotIndex = index
        director.shotStart = start
        director.startCam = director.lastCam
        if (s.source)
            director.scene.source = director.sibling(s.source)
        director.layerFlags.offsideLines = s.lines
        director.layerFlags.walls = s.walls
        director.layerFlags.labels = s.labels
        director.layerFlags.uncertainty = true
        director.layerFlags.highlights = true
        director.host.showBadge = s.badge
        director.caption = s.caption || ""
        director.titleText = s.title || ""
        director.subtitleText = (director.portrait && s.subtitlePortrait) || s.subtitle || ""
    }

    function step() {
        const t = director.frame / director.fps
        if (t >= director.total) {
            recorder.finish()
            Qt.quit()
            return
        }
        let start = 0, index = 0
        while (t >= start + shots[index].dur) {
            start += shots[index].dur
            index++
        }
        if (index !== director.shotIndex)
            beginShot(index, start)
        const s = shots[index]
        const local = t - start
        const u = local / s.dur

        director.scene.position = s.position(u)
        // Smooth ball following (no jumps when the ball changes direction)
        if (director.scene.ballVisible) {
            const b = director.scene.ballPosition
            director.follow = director.frame === 0 ? b
                            : Qt.vector3d(mix(director.follow.x, b.x, 0.08), 0, mix(director.follow.z, b.z, 0.08))
        }
        const c = s.camera(u, local)
        director.lastCam = c
        director.rig.target = c.target
        director.rig.yaw = c.yaw
        // In portrait, more top-down so the pitch fills the tall frame instead of the stand
        director.rig.pitch = director.portrait ? Math.max(-89.5, c.pitch - 12) : c.pitch
        director.rig.distance = c.distance

        director.captionOpacity = director.caption !== "" ? fade(local, s.dur) : 0
        director.titleOpacity = director.titleText !== "" ? (index === 0 ? Math.min(1, (s.dur - local) / 0.7)
                                                                        : Math.min(1, local / 0.7)) : 0
        director.blackOpacity = index === shots.length - 1 ? Math.max(0, (local - (s.dur - 0.6)) / 0.6) : 0

        // Render the stage at its exact size and continue when the image is ready
        const ok = director.stage.grabToImage(function (result) {
            recorder.writeImage(result.image)
            director.frame++
            if (director.frame % (5 * director.fps) === 0)
                console.warn(`Grabando: ${(director.frame / director.fps).toFixed(0)} de ${director.total} s`)
            ticker.start()
        }, Qt.size(director.stage.width, director.stage.height))
        if (!ok) {
            console.warn("No se pudo capturar el fotograma", director.frame)
            Qt.quit()
        }
    }

    Timer {
        id: ticker
        interval: 1
        onTriggered: director.step()
    }
    // Wait until the scene and textures are ready before the first frame
    Timer {
        interval: 2500
        running: true
        onTriggered: {
            recorder.start(director.output, director.fps, director.stage.width, director.stage.height)
            ticker.start()
        }
    }

    // Lower caption
    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: director.portrait ? 54 : 48
        anchors.bottomMargin: director.portrait ? 360 : 48
        width: Math.min(parent.width - 2 * anchors.leftMargin, captionText.implicitWidth + 44)
        height: captionText.implicitHeight + 26
        radius: 6
        color: Qt.rgba(0.04, 0.06, 0.08, 0.82)
        opacity: director.captionOpacity
        Rectangle { width: 5; height: parent.height; radius: 2; color: "#64d2ff" }
        Text {
            id: captionText
            anchors.verticalCenter: parent.verticalCenter
            x: 24
            width: Math.min(implicitWidth, director.width - 2 * parent.anchors.leftMargin - 44)
            text: director.caption
            color: "white"
            font.pixelSize: director.portrait ? 38 : 26
            wrapMode: Text.WordWrap
        }
    }

    // Opening and closing titles
    Rectangle {
        anchors.fill: parent
        opacity: director.titleOpacity
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0.04, 0.06, 0.08, 0.35) }
            GradientStop { position: 0.5; color: Qt.rgba(0.04, 0.06, 0.08, 0.75) }
            GradientStop { position: 1.0; color: Qt.rgba(0.04, 0.06, 0.08, 0.35) }
        }
        Column {
            anchors.centerIn: parent
            width: parent.width - 120
            spacing: 22
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: director.titleText
                color: "white"
                font.pixelSize: director.portrait ? 84 : 68
                font.bold: true
            }
            Rectangle { anchors.horizontalCenter: parent.horizontalCenter; width: 120; height: 4; radius: 2; color: "#64d2ff" }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: director.subtitleText
                color: "#d1d7dd"
                font.pixelSize: director.portrait ? 36 : 28
                lineHeight: 1.3
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "black"
        opacity: director.blackOpacity
    }
}
