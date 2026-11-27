import QtQuick
import QtQuick3D
import QtQuick.Controls
// After QtQuick3D, which also defines a "Material" type and would shadow it
import QtQuick.Controls.Material
import QtQuick.Dialogs
import QtQuick.Layouts
import OffsideViewer

ApplicationWindow {
    id: window

    // Command-line arguments (see main.cpp)
    property url initialSource
    property int initialFrame: -1
    property string initialCamera: ""
    property int initialFocus: -1
    property bool instantCamera: false
    property bool autoPlay: false
    // Command-line analysis (--input ...): source and steps to run in the Analysis tab
    property var initialInput: []
    property var initialAnalysis: ({})
    // For --screenshot: true once the window can be captured
    property bool captureReady: initialInput.length === 0
    // Demo video mode (--demo output.mp4): no UI and a scripted camera
    property string demoOutput: ""
    property int demoWidth: 1920
    property int demoHeight: 1080
    readonly property bool demo: demoOutput !== ""
    readonly property bool portrait: demoHeight > demoWidth
    // 2D labels are enlarged in the video so they are readable on a phone screen
    readonly property real overlayScale: demo ? (portrait ? 1.9 : 1.4) : 1
    property bool showBadge: true

    // In demo mode the view renders at the exact video resolution even if the window is smaller (a
    // portrait video does not fit on a landscape screen)
    Item {
        id: demoStage
        visible: window.demo
        width: window.demoWidth
        height: window.demoHeight
        z: 100
    }

    width: 1600
    height: 940
    visible: true
    title: controller.loaded ? "Visor de fuera de juego — " + controller.title : "Visor de fuera de juego"
    color: "#0e1418"

    Material.theme: Material.Dark
    Material.accent: "#64d2ff"
    Material.primary: "#1b2630"
    Material.background: "#141c22"

    property bool started: false

    AnalysisBackend {
        id: backend
    }

    // 0: analysis of a play (video or images); 1: 3D viewer of the result
    property int page: (initialSource.toString() !== "" && initialInput.length === 0) || demo ? 1 : 0

    SceneController {
        id: controller
        // Opening another analysis returns to the broadcast view
        onDataChanged: if (window.started && !window.demo) window.applyCamera("transmision")
    }

    QtObject {
        id: layers
        property bool skeletons: true
        property bool lowConfidence: true
        property bool labels: true
        property bool ball: true
        property bool offsideLines: true
        property bool walls: false
        property bool uncertainty: true
        property bool highlights: true
        property bool shadows: true
        property bool followBall: false
    }

    Component.onCompleted: {
        if (initialInput.length > 0)
            analysisPage.runScript(initialInput, initialAnalysis, () => captureReady = true)
        if (demo) {
            viewport.parent = demoStage
            viewport.anchors.fill = demoStage
        }
        if (initialSource.toString() !== "") {
            controller.source = initialSource
            if (initialFrame >= 0)
                controller.seekFrameNumber(initialFrame)
            controller.playing = autoPlay
        }
        // Wait until the view has a size before framing the camera
        Qt.callLater(() => {
            if (demo)
                return
            if (initialFocus >= 0)
                focusEntity(controller.entityIndexForId(initialFocus))
            else
                applyCamera(initialCamera !== "" ? initialCamera : "transmision")
            started = true
        })
    }

    // Close-up of an entity at the current instant
    function focusEntity(entity) {
        if (entity < 0)
            return
        layers.followBall = false
        const g = controller.entityGround(entity)
        orbit.moveTo(Qt.vector3d(g.x, 95, g.z), -35, -14, 750)
    }

    // Preset views. Scene units: cm
    function applyCamera(name) {
        const info = controller.eventInfo
        const hasEvent = info.valid === true
        const lineX = hasEvent ? info.lineX : 0
        const dir = hasEvent ? info.attackDirection : 1
        layers.followBall = false
        switch (name) {
        case "cenital": {
            const aspect = Math.max(0.5, view.width / Math.max(1, view.height))
            const tanHalf = Math.tan(orbit.fieldOfView / 2 * Math.PI / 180)
            const d = Math.max((controller.pitchWidth + 12) / (2 * tanHalf),
                               (controller.pitchLength + 12) / (2 * tanHalf * aspect)) * 100
            orbit.moveTo(Qt.vector3d(0, 0, 0), 0, -89.5, d)
            break
        }
        case "linea":
            // From the touchline, aligned with the line: it looks vertical, as in VAR
            orbit.moveTo(Qt.vector3d(lineX, 120, 0), 0, -14, 5200)
            break
        case "porteria":
            orbit.moveTo(Qt.vector3d(dir * 2300, 0, 0), dir > 0 ? 90 : -90, -19, 4300)
            break
        case "atacante":
            if (hasEvent)
                focusEntity(info.receiverEntity)
            break
        default: // broadcast
            orbit.moveTo(Qt.vector3d(lineX * 0.55, 0, 600), 0, -27, 7600)
        }
    }

    FileDialog {
        id: openDialog
        title: "Abrir análisis de jugada"
        nameFilters: ["Análisis de jugada (*.json)", "Todos los archivos (*)"]
        onAccepted: controller.source = selectedFile
    }

    Shortcut { sequence: "Space"; enabled: window.page === 1; onActivated: controller.togglePlay() }
    Shortcut { sequence: "Left"; enabled: window.page === 1; onActivated: controller.stepFrames(-1) }
    Shortcut { sequence: "Right"; enabled: window.page === 1; onActivated: controller.stepFrames(1) }
    Shortcut { sequence: "Shift+Left"; enabled: window.page === 1; onActivated: controller.stepFrames(-10) }
    Shortcut { sequence: "Shift+Right"; enabled: window.page === 1; onActivated: controller.stepFrames(10) }
    Shortcut { sequence: "Home"; enabled: window.page === 1; onActivated: controller.position = 0 }
    Shortcut { sequence: "End"; enabled: window.page === 1; onActivated: controller.position = controller.frameCount - 1 }
    Shortcut { sequence: "P"; enabled: window.page === 1; onActivated: controller.goToEvent(controller.selectedEvent) }
    Shortcut { sequence: "1"; enabled: window.page === 1; onActivated: window.applyCamera("transmision") }
    Shortcut { sequence: "2"; enabled: window.page === 1; onActivated: window.applyCamera("cenital") }
    Shortcut { sequence: "3"; enabled: window.page === 1; onActivated: window.applyCamera("linea") }
    Shortcut { sequence: "4"; enabled: window.page === 1; onActivated: window.applyCamera("porteria") }
    Shortcut { sequence: "5"; enabled: window.page === 1; onActivated: window.applyCamera("atacante") }
    Shortcut { sequence: StandardKey.Open; onActivated: openDialog.open() }

    header: ToolBar {
        visible: !window.demo
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 4

            TabBar {
                currentIndex: window.page
                onCurrentIndexChanged: window.page = currentIndex
                Material.background: "transparent"
                TabButton { text: "Análisis"; width: implicitWidth + 24 }
                TabButton { text: "Vista 3D"; width: implicitWidth + 24 }
            }
            ToolButton {
                visible: window.page === 1
                text: "Abrir análisis…"
                onClicked: openDialog.open()
            }
            Label {
                Layout.fillWidth: true
                text: window.page === 0 ? "" : controller.loaded ? controller.title : "Ningún análisis cargado"
                elide: Text.ElideRight
                font.bold: true
                leftPadding: 8
            }
            Label { text: "Vista:"; color: "#a0a7ad"; visible: window.page === 1 }
            Repeater {
                model: [
                    { key: "transmision", text: "Transmisión", shortcut: "1" },
                    { key: "cenital", text: "Cenital", shortcut: "2" },
                    { key: "linea", text: "Línea", shortcut: "3" },
                    { key: "porteria", text: "Portería", shortcut: "4" },
                    { key: "atacante", text: "Atacante", shortcut: "5" }
                ]
                delegate: ToolButton {
                    required property var modelData
                    visible: window.page === 1
                    text: modelData.text
                    enabled: controller.loaded
                    onClicked: window.applyCamera(modelData.key)
                    ToolTip.visible: hovered
                    ToolTip.text: "Tecla " + modelData.shortcut
                }
            }
            ToolButton {
                visible: window.page === 1
                text: "Seguir balón"
                checkable: true
                checked: layers.followBall
                enabled: controller.loaded
                onToggled: layers.followBall = checked
            }
        }
    }

    footer: TimelineBar { controller: controller; visible: !window.demo && window.page === 1 }

    StackLayout {
        anchors.fill: parent
        currentIndex: window.page

        AnalysisPage {
            id: analysisPage
            backend: backend
            onShowIn3D: (jsonPath) => {
                controller.source = backend.fileUrl(jsonPath)
                window.page = 1
            }
        }

        RowLayout {
            spacing: 0

            Item {
                id: viewport
                Layout.fillWidth: true
                Layout.fillHeight: true

                View3D {
                    id: view
                    anchors.fill: parent
                    camera: orbit.camera

                    environment: SceneEnvironment {
                        clearColor: "#0e1418"
                        backgroundMode: SceneEnvironment.Color
                        antialiasingMode: SceneEnvironment.MSAA
                        antialiasingQuality: SceneEnvironment.VeryHigh
                        aoStrength: 40
                        aoDistance: 25
                        aoSoftness: 40
                    }

                    OrbitCameraRig {
                        id: orbit
                        instant: window.instantCamera
                        // Portrait video: same visible width as landscape (~62° horizontal FOV)
                        fieldOfViewOrientation: window.portrait ? PerspectiveCamera.Horizontal : PerspectiveCamera.Vertical
                        fieldOfView: window.portrait ? 54 : 38
                        yaw: 0
                        pitch: -27
                        distance: 7600
                    }

                    DirectionalLight {
                        // The shadow is computed from the light position: it must be above everything.
                        // Side light relative to the usual cameras (from the touchline): shadows are seen from the side
                        // instead of hidden behind each player
                        position: Qt.vector3d(0, 9000, 0)
                        eulerRotation: Qt.vector3d(-48, 65, 0)
                        brightness: 1.15
                        ambientColor: Qt.rgba(0.40, 0.42, 0.45, 1.0)
                        castsShadow: layers.shadows
                        shadowMapQuality: Light.ShadowMapQualityVeryHigh
                        shadowMapFar: 30000
                        shadowFactor: 60
                        // shadowBias stays at 0: in Qt 6.4 it ranges from 0 to 1 and at 1 no shadow is drawn at all
                    }
                    DirectionalLight {
                        eulerRotation: Qt.vector3d(-35, -115, 0)
                        brightness: 0.35
                    }

                    PitchScene {
                        pitchLength: controller.pitchLength > 0 ? controller.pitchLength : 105
                        pitchWidth: controller.pitchWidth > 0 ? controller.pitchWidth : 68
                    }

                    SkeletonLayer {
                        visible: layers.skeletons
                        controller: controller
                        showLowConfidence: layers.lowConfidence
                        showShadows: layers.shadows
                    }

                    // Discs under the players of the play (passer, attacker, defender)
                    Repeater3D {
                        model: layers.highlights ? controller.highlights.length : 0
                        delegate: Model {
                            required property int index
                            readonly property var entry: controller.highlights[index]
                            visible: entry !== undefined
                            source: "#Cylinder"
                            position: entry ? entry.position.plus(Qt.vector3d(0, 3, 0)) : Qt.vector3d(0, 0, 0)
                            scale: Qt.vector3d(1.6, 0.004, 1.6)
                            castsShadows: false
                            receivesShadows: false
                            materials: PrincipledMaterial {
                                lighting: PrincipledMaterial.NoLighting
                                alphaMode: PrincipledMaterial.Blend
                                baseColor: entry ? Qt.rgba(entry.color.r, entry.color.g, entry.color.b, 0.45) : "transparent"
                            }
                        }
                    }

                    // Ball and trail
                    Model {
                        visible: layers.ball && controller.ballVisible
                        source: "#Sphere"
                        position: controller.ballPosition
                        scale: Qt.vector3d(0.22, 0.22, 0.22)
                        materials: PrincipledMaterial { baseColor: "#fbfbfb"; roughness: 0.35 }
                    }
                    Repeater3D {
                        model: layers.ball ? controller.ballTrail.length : 0
                        delegate: Model {
                            required property int index
                            readonly property var entry: controller.ballTrail[index]
                            visible: entry !== undefined
                            source: "#Sphere"
                            position: entry ? entry.position : Qt.vector3d(0, 0, 0)
                            scale: Qt.vector3d(0.1, 0.1, 0.1)
                            castsShadows: false
                            materials: PrincipledMaterial {
                                lighting: PrincipledMaterial.NoLighting
                                alphaMode: PrincipledMaterial.Blend
                                baseColor: Qt.rgba(1, 1, 1, entry ? entry.alpha : 0)
                            }
                        }
                    }

                    OffsideOverlay {
                        visible: layers.offsideLines && controller.eventInfo.valid === true
                        info: controller.eventInfo
                        pitchWidth: controller.pitchWidth
                        showUncertainty: layers.uncertainty
                        showWalls: layers.walls
                    }
                }

                // Mouse: left rotates, right/middle pans, wheel zooms
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                    property point last
                    onPressed: (mouse) => {
                        last = Qt.point(mouse.x, mouse.y)
                        layers.followBall = false
                    }
                    onPositionChanged: (mouse) => {
                        const dx = mouse.x - last.x, dy = mouse.y - last.y
                        last = Qt.point(mouse.x, mouse.y)
                        if (mouse.buttons & Qt.LeftButton)
                            orbit.orbitBy(dx, dy)
                        else
                            orbit.panBy(dx, dy)
                    }
                    onWheel: (wheel) => orbit.zoomBy(wheel.angleDelta.y / 120)
                }

                Connections {
                    target: controller
                    function onStateChanged() {
                        if (!layers.followBall || !controller.ballVisible || orbit.animating)
                            return
                        const b = controller.ballPosition
                        const goal = Qt.vector3d(b.x, 0, b.z)
                        orbit.target = orbit.target.plus(goal.minus(orbit.target).times(0.12))
                    }
                }

                PlayerLabels {
                    anchors.fill: parent
                    visible: layers.labels
                    view: view
                    labels: controller.labels
                    tagScale: window.overlayScale
                }

                // Ring around the ball: in far views the ball covers very few pixels
                Item {
                    readonly property vector3d screen: {
                        orbit.camera.scenePosition; orbit.camera.sceneRotation; view.width; view.height
                        return view.camera ? view.mapFrom3DScene(controller.ballPosition) : Qt.vector3d(0, 0, -1)
                    }
                    visible: layers.ball && controller.ballVisible && screen.z > 2500
                    x: screen.x
                    y: screen.y
                    Rectangle {
                        x: -7; y: -7; width: 14; height: 14; radius: 7
                        color: "transparent"
                        border.color: "white"
                        border.width: 2
                    }
                }

                // Body points that define each line: marked in 2D so the body itself does not hide them
                Repeater {
                    readonly property var info: controller.eventInfo
                    readonly property bool active: layers.offsideLines && info.valid === true
                                                   && controller.frameIndex === info.frameIndex
                    model: active ? [
                        { point: info.attackerPoint, show: info.attackerHasPoint, color: "#ff3b30",
                          text: info.attackerJoint },
                        { point: info.defenderPoint, show: info.defenderHasPoint && !info.lineFromBall, color: "#2f8cff",
                          text: info.defenderJoint }
                    ] : []
                    delegate: Item {
                        required property var modelData
                        readonly property vector3d screen: {
                            orbit.camera.scenePosition; orbit.camera.sceneRotation; view.width; view.height
                            return view.camera ? view.mapFrom3DScene(modelData.point) : Qt.vector3d(0, 0, -1)
                        }
                        visible: modelData.show && screen.z > 0
                        x: screen.x
                        y: screen.y
                        z: 3
                        scale: window.overlayScale
                        Rectangle {
                            x: -10; y: -10; width: 20; height: 20; radius: 10
                            color: "transparent"
                            border.color: modelData.color
                            border.width: 2.5
                        }
                        Rectangle { x: -2.5; y: -2.5; width: 5; height: 5; radius: 2.5; color: modelData.color }
                        Rectangle {
                            x: 14
                            y: -26
                            width: jointText.implicitWidth + 10
                            height: jointText.implicitHeight + 4
                            radius: 3
                            color: Qt.rgba(0.05, 0.07, 0.09, 0.88)
                            border.color: modelData.color
                            Text {
                                id: jointText
                                anchors.centerIn: parent
                                text: modelData.text
                                color: "white"
                                font.pixelSize: 11
                            }
                        }
                    }
                }

                StatusBadge {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    // In the portrait video, outside the top strip covered by social media overlays
                    anchors.leftMargin: window.demo && window.portrait ? 54 : 14
                    anchors.topMargin: window.demo && window.portrait ? 300 : 14
                    visible: controller.eventInfo.valid === true && layers.offsideLines && window.showBadge
                    scale: window.demo ? (window.portrait ? 2.1 : 1.4) : 1
                    transformOrigin: Item.TopLeft
                    info: controller.eventInfo
                }

                Rectangle {
                    visible: controller.synthetic
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.top
                    anchors.topMargin: window.demo && window.portrait ? 230 : 14
                    scale: window.demo && window.portrait ? 1.8 : 1
                    color: Qt.rgba(1, 0.84, 0.04, 0.16)
                    border.color: "#ffd60a"
                    radius: 4
                    width: syntheticText.implicitWidth + 20
                    height: syntheticText.implicitHeight + 8
                    Text {
                        id: syntheticText
                        anchors.centerIn: parent
                        text: "DATOS SINTÉTICOS · posiciones y poses generadas, no medidas"
                        color: "#ffd60a"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }

                // Legend
                Rectangle {
                    visible: controller.loaded && !window.demo
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 14
                    color: Qt.rgba(0.05, 0.07, 0.09, 0.8)
                    radius: 6
                    width: legend.implicitWidth + 20
                    height: legend.implicitHeight + 14
                    Column {
                        id: legend
                        anchors.centerIn: parent
                        spacing: 3
                        component Entry: Row {
                            property color swatch
                            property string label
                            property real swatchOpacity: 1
                            spacing: 6
                            Rectangle {
                                width: 16; height: 6; radius: 2
                                anchors.verticalCenter: parent.verticalCenter
                                color: Qt.rgba(swatch.r, swatch.g, swatch.b, swatchOpacity)
                            }
                            Text { text: label; color: "#d1d1d6"; font.pixelSize: 11 }
                        }
                        Entry { swatch: "#2f8cff"; label: "Línea de fuera de juego (penúltimo defensor o balón)" }
                        Entry { swatch: "#2f8cff"; swatchOpacity: 0.35; label: "Banda de incertidumbre" }
                        Entry { swatch: "#ff3b30"; label: "Parte válida más adelantada del atacante" }
                        Entry { swatch: "#ffffff"; swatchOpacity: 0.35; label: "Translúcido: confianza baja · ~: solo posición, sin pose" }
                    }
                }

                Text {
                    visible: !window.demo
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 14
                    text: "Arrastrar: girar · Botón derecho: desplazar · Rueda: zoom · Espacio: reproducir · ←/→: fotograma"
                    color: "#8e8e93"
                    font.pixelSize: 11
                }

                // No data or load error
                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    visible: !controller.loaded || controller.errorString !== ""
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: controller.errorString !== "" ? controller.errorString : "Abre un análisis de jugada (.json) para empezar"
                        color: controller.errorString !== "" ? "#ff6961" : "#d1d1d6"
                        font.pixelSize: 16
                    }
                    Button {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Abrir análisis…"
                        highlighted: true
                        onClicked: openDialog.open()
                    }
                }

                Loader {
                    anchors.fill: parent
                    active: window.demo
                    sourceComponent: DemoDirector {
                        scene: controller
                        rig: orbit
                        layerFlags: layers
                        host: window
                        stage: viewport
                        portrait: window.portrait
                        output: window.demoOutput
                        firstSource: window.initialSource
                    }
                }
            }

            SidePanel {
                visible: !window.demo
                Layout.preferredWidth: 350
                Layout.fillHeight: true
                controller: controller
                layers: layers
            }
        }
    }
}
