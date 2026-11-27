import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Dialogs
import QtQuick.Layouts

// Analysis of a play: a video or images are loaded, the user picks the pass frame, that frame is
// calibrated and players are detected; then the user picks the attacked goal, the attacker and the
// second-last defender, and Law 11 is applied. The result opens in the 3D view.
Item {
    id: page

    required property var backend
    signal showIn3D(string jsonPath)

    property var source: null // open response
    property int index: 0 // frame being shown (0..count-1)
    property int number: 0 // its number in the video or in the file name
    property url frameUrl
    property bool frameLoading: false
    property int pendingFrame: -1

    property var prep: null // prepare response
    property int prepIndex: -1
    property int direction: 0 // +1 attacks towards the right goal (+X)
    property int attacker: -1
    property int defender: -1
    property bool defenderManual: false
    property string defenderReason: ""
    property string pickMode: "attacker" // attacker, defender or ball
    property string ballMode: "auto" // auto (detector), manual (click) or none (no ball)
    property var ballPoint: null // [u, v] in video pixels if ballMode is manual
    property var result: null // analyze response
    property bool showLines: true
    property bool showVar: false
    property string errorText: ""

    readonly property bool overlayActive: prep !== null && prepIndex === index && !showVar
    readonly property bool calibrated: prep !== null && prep.calibration.ok
    readonly property bool ready: calibrated && direction !== 0 && attacker > 0 && defender > 0 && attacker !== defender

    // Pending response for each request
    property var handlers: ({})
    function call(command, args, onReply) {
        const id = backend.request(command, args)
        handlers[id] = onReply
    }
    Connections {
        target: page.backend
        function onReplied(id, reply) {
            const handler = page.handlers[id]
            delete page.handlers[id]
            if (handler)
                handler(reply)
        }
    }

    function openPaths(paths) {
        errorText = ""
        call("open", { paths: paths }, reply => {
            if (!reply.ok) {
                errorText = reply.error
                return
            }
            source = reply
            prep = null
            prepIndex = -1
            result = null
            showFrame(0)
        })
    }

    function showFrame(i) {
        if (!source)
            return
        i = Math.max(0, Math.min(source.count - 1, i))
        index = i
        showVar = false
        if (frameLoading) {
            pendingFrame = i
            return
        }
        frameLoading = true
        call("frame", { index: i }, reply => {
            frameLoading = false
            if (reply.ok) {
                frameUrl = backend.fileUrl(reply.path)
                number = reply.number
            } else {
                errorText = reply.error
            }
            if (pendingFrame >= 0 && pendingFrame !== reply.index) {
                const next = pendingFrame
                pendingFrame = -1
                showFrame(next)
            } else {
                pendingFrame = -1
            }
        })
    }

    function prepare(onDone) {
        errorText = ""
        result = null
        attacker = -1
        defender = -1
        defenderManual = false
        defenderReason = ""
        pickMode = "attacker"
        ballMode = "auto"
        ballPoint = null
        const i = index
        call("prepare", { index: i }, reply => {
            if (!reply.ok) {
                errorText = reply.error
            } else {
                prep = reply
                prepIndex = i
                minimap.requestPaint()
                linesCanvas.requestPaint()
            }
            if (onDone)
                onDone()
        })
    }

    function player(id) {
        if (!prep)
            return null
        for (const p of prep.players)
            if (p.id === id)
                return p
        return null
    }

    function proposeDefender(onDone) {
        if (defenderManual || attacker <= 0 || direction === 0 || !calibrated) {
            if (onDone)
                onDone()
            return
        }
        call("propose", { index: prepIndex, direction: direction, attacker: attacker }, reply => {
            if (reply.ok && !defenderManual) {
                defender = reply.defender !== null && reply.defender !== undefined ? reply.defender : -1
                defenderReason = reply.reason
            }
            if (onDone)
                onDone()
        })
    }

    function choose(id) {
        result = null
        if (pickMode === "attacker") {
            attacker = id
            if (defender === id)
                defender = -1
            pickMode = "defender"
            proposeDefender()
        } else if (pickMode === "defender") {
            defender = id
            defenderManual = true
            defenderReason = "Elegido a mano"
            if (attacker === id)
                attacker = -1
        }
    }

    function setDirection(d) {
        direction = d
        result = null
        proposeDefender()
    }

    function analyze(onDone) {
        errorText = ""
        const ball = ballMode === "manual" ? ballPoint : ballMode
        call("analyze", { index: prepIndex, attacker: attacker, defender: defender, direction: direction, ball: ball }, reply => {
            if (!reply.ok)
                errorText = reply.error
            else
                result = reply
            if (onDone)
                onDone()
        })
    }

    // The same steps as with the buttons, from the command line (main.cpp): opens the source, goes to
    // the frame and, if given, calibrates, picks goal and players and applies the rule.
    // opts: {frame, prepare, goal: "left"/"right", attacker, defender}
    function runScript(paths, opts, done) {
        call("open", { paths: paths }, reply => {
            if (!reply.ok) {
                errorText = reply.error
                done()
                return
            }
            source = reply
            const args = opts.frame >= 0 ? { number: opts.frame } : { index: 0 }
            call("frame", args, frame => {
                if (!frame.ok) {
                    errorText = frame.error
                    done()
                    return
                }
                index = frame.index
                number = frame.number
                frameUrl = backend.fileUrl(frame.path)
                if (!opts.prepare) {
                    done()
                    return
                }
                prepare(() => {
                    if (!calibrated || opts.goal === "") {
                        done()
                        return
                    }
                    direction = opts.goal === "right" ? 1 : -1
                    if (opts.attacker <= 0) {
                        done()
                        return
                    }
                    attacker = opts.attacker
                    pickMode = "defender"
                    if (opts.defender > 0) {
                        defender = opts.defender
                        defenderManual = true
                        defenderReason = "Elegido a mano"
                    }
                    proposeDefender(() => defender > 0 ? analyze(done) : done())
                })
            })
        })
    }

    function teamColor(p) {
        if (p.role === "referee")
            return "#ffd60a"
        if (p.role === "goalkeeper")
            return "#bf5af2"
        if (p.team !== null && p.team !== undefined && prep.team_colors[p.team])
            return prep.team_colors[p.team]
        return "#8e8e93"
    }

    function statusText(r) {
        if (!r)
            return ""
        if (r.status === "offside")
            return r.within_uncertainty ? "FUERA DE JUEGO (no concluyente)" : "FUERA DE JUEGO"
        if (r.status === "onside")
            return r.within_uncertainty ? "POSICIÓN LEGAL (no concluyente)" : "POSICIÓN LEGAL"
        return "NO EVALUABLE"
    }

    Shortcut { sequence: "Left"; enabled: page.visible; onActivated: page.showFrame(page.index - 1) }
    Shortcut { sequence: "Right"; enabled: page.visible; onActivated: page.showFrame(page.index + 1) }
    Shortcut { sequence: "Shift+Left"; enabled: page.visible; onActivated: page.showFrame(page.index - 10) }
    Shortcut { sequence: "Shift+Right"; enabled: page.visible; onActivated: page.showFrame(page.index + 10) }

    FileDialog {
        id: videoDialog
        title: "Abrir vídeo"
        nameFilters: ["Vídeos (*.mp4 *.mkv *.avi *.mov *.webm *.m4v *.ts)", "Todos los archivos (*)"]
        onAccepted: page.openPaths([page.backend.localPath(selectedFile)])
    }
    FileDialog {
        id: imagesDialog
        title: "Abrir una o varias imágenes"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Imágenes (*.jpg *.jpeg *.png *.bmp)", "Todos los archivos (*)"]
        onAccepted: {
            const paths = []
            for (let i = 0; i < selectedFiles.length; ++i)
                paths.push(page.backend.localPath(selectedFiles[i]))
            page.openPaths(paths)
        }
    }
    FolderDialog {
        id: folderDialog
        title: "Abrir una carpeta de imágenes (fotogramas)"
        onAccepted: page.openPaths([page.backend.localPath(selectedFolder)])
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Frame with numbered boxes and calibrated pitch lines
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Item {
                id: stage
                Layout.fillWidth: true
                Layout.fillHeight: true

                Image {
                    id: frameView
                    anchors.fill: parent
                    anchors.margins: 8
                    fillMode: Image.PreserveAspectFit
                    source: page.showVar && page.result ? page.backend.fileUrl(page.result.image) : page.frameUrl
                    cache: false
                    smooth: true
                }

                // Same rectangle as the image; s maps original pixels to screen
                Item {
                    id: overlay
                    readonly property real s: page.source ? frameView.paintedWidth / page.source.width : 1
                    x: frameView.x + (frameView.width - frameView.paintedWidth) / 2
                    y: frameView.y + (frameView.height - frameView.paintedHeight) / 2
                    width: frameView.paintedWidth
                    height: frameView.paintedHeight
                    visible: page.overlayActive

                    Canvas {
                        id: linesCanvas
                        anchors.fill: parent
                        visible: page.showLines && page.calibrated
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.reset()
                            if (!page.prep || !page.prep.calibration.ok)
                                return
                            const s = overlay.s
                            ctx.strokeStyle = Qt.rgba(1, 0.18, 0.83, 0.85)
                            ctx.lineWidth = 2
                            for (const line of page.prep.calibration.lines) {
                                ctx.beginPath()
                                ctx.moveTo(line[0][0] * s, line[0][1] * s)
                                for (let i = 1; i < line.length; ++i)
                                    ctx.lineTo(line[i][0] * s, line[i][1] * s)
                                ctx.stroke()
                            }
                        }
                    }

                    Repeater {
                        model: page.overlayActive ? page.prep.players : []
                        delegate: Rectangle {
                            required property var modelData
                            readonly property bool isAttacker: modelData.id === page.attacker
                            readonly property bool isDefender: modelData.id === page.defender
                            x: modelData.box[0] * overlay.s
                            y: modelData.box[1] * overlay.s
                            width: (modelData.box[2] - modelData.box[0]) * overlay.s
                            height: (modelData.box[3] - modelData.box[1]) * overlay.s
                            color: hover.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent"
                            border.width: isAttacker || isDefender ? 3 : 1.5
                            border.color: isAttacker ? "#ff3b30" : isDefender ? "#2f8cff" : page.teamColor(modelData)
                            Rectangle {
                                anchors.bottom: parent.top
                                anchors.left: parent.left
                                anchors.bottomMargin: 2
                                width: tag.implicitWidth + 8
                                height: tag.implicitHeight + 2
                                radius: 3
                                color: parent.isAttacker ? "#ff3b30" : parent.isDefender ? "#2f8cff" : Qt.rgba(0.05, 0.07, 0.09, 0.85)
                                Text {
                                    id: tag
                                    anchors.centerIn: parent
                                    text: modelData.id + (parent.parent.isAttacker ? " atacante" : parent.parent.isDefender ? " defensor" : "")
                                    color: "white"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                            MouseArea {
                                id: hover
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.choose(modelData.id)
                            }
                        }
                    }

                    // Ball: the detector's (white) or the one marked by hand (orange)
                    Rectangle {
                        readonly property var b: page.ballMode === "manual" && page.ballPoint
                                                  ? [page.ballPoint[0], page.ballPoint[1], page.ballPoint[0], page.ballPoint[1]]
                                                  : page.prep && page.prep.ball ? page.prep.ball.box : [0, 0, 0, 0]
                        visible: page.overlayActive && page.ballMode !== "none"
                                 && (page.ballMode === "manual" ? page.ballPoint !== null : page.prep.ball !== null)
                        x: (b[0] + b[2]) / 2 * overlay.s - 9
                        y: (b[1] + b[3]) / 2 * overlay.s - 9
                        width: 18; height: 18; radius: 9
                        color: "transparent"
                        border.color: page.ballMode === "manual" ? "#ff9f0a" : "white"
                        border.width: 3
                    }

                    // Mark the ball: one click anywhere (also inside a player's box)
                    MouseArea {
                        anchors.fill: parent
                        enabled: page.overlayActive && page.pickMode === "ball"
                        visible: enabled
                        cursorShape: Qt.CrossCursor
                        onClicked: mouse => {
                            page.ballPoint = [mouse.x / overlay.s, mouse.y / overlay.s]
                            page.ballMode = "manual"
                            page.result = null
                        }
                    }
                }

                // No source open
                Column {
                    anchors.centerIn: parent
                    spacing: 14
                    visible: !page.source
                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Abre un vídeo o imágenes de la jugada"
                        font.pixelSize: 18
                        color: "#d1d1d6"
                    }
                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 10
                        Button { text: "Vídeo…"; highlighted: true; onClicked: videoDialog.open() }
                        Button { text: "Imágenes…"; onClicked: imagesDialog.open() }
                        Button { text: "Carpeta de fotogramas…"; onClicked: folderDialog.open() }
                    }
                }

                Label {
                    visible: page.showVar
                    anchors.top: parent.top
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.topMargin: 14
                    text: "Imagen del pase con las líneas (pulsa «Imagen del VAR» para volver)"
                    color: "#d1d1d6"
                    background: Rectangle { color: Qt.rgba(0.05, 0.07, 0.09, 0.8); radius: 4 }
                    padding: 6
                }
            }

            // Frame navigation
            Pane {
                Layout.fillWidth: true
                visible: page.source !== null && page.source.count > 1
                padding: 6
                RowLayout {
                    anchors.fill: parent
                    spacing: 4
                    ToolButton { text: "⏮"; onClicked: page.showFrame(0) }
                    ToolButton { text: "−10"; onClicked: page.showFrame(page.index - 10) }
                    ToolButton { text: "◀"; onClicked: page.showFrame(page.index - 1) }
                    Slider {
                        id: slider
                        Layout.fillWidth: true
                        from: 0
                        to: page.source ? page.source.count - 1 : 1
                        stepSize: 1
                        value: page.index
                        onMoved: page.showFrame(Math.round(value))
                    }
                    ToolButton { text: "▶"; onClicked: page.showFrame(page.index + 1) }
                    ToolButton { text: "+10"; onClicked: page.showFrame(page.index + 10) }
                    ToolButton { text: "⏭"; onClicked: page.showFrame(page.source.count - 1) }
                    Label {
                        text: "Fotograma " + page.number + "  (" + (page.index + 1) + "/" + (page.source ? page.source.count : 0) + ")"
                        font.family: "monospace"
                        Layout.preferredWidth: 230
                        horizontalAlignment: Text.AlignRight
                    }
                }
            }
        }

        // Analysis steps
        Pane {
            Layout.preferredWidth: 380
            Layout.fillHeight: true
            padding: 0
            Material.background: "#18222a"

            ScrollView {
                anchors.fill: parent
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 10

                    component Heading: Label {
                        Layout.topMargin: 6
                        font.bold: true
                        font.pixelSize: 13
                        color: "#64d2ff"
                    }
                    component Note: Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        color: "#a0a7ad"
                        font.pixelSize: 12
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.margins: 14
                        spacing: 8

                        Heading { text: "FUENTE" }
                        Label {
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                            text: page.source ? page.source.name : "Nada abierto"
                            font.bold: true
                        }
                        Note {
                            visible: page.source !== null
                            text: page.source ? (page.source.kind === "video" ? "Vídeo" : page.source.kind === "image" ? "Imagen" : "Imágenes")
                                                + " · " + page.source.count + " fotograma" + (page.source.count === 1 ? "" : "s")
                                                + " · " + page.source.width + "×" + page.source.height : ""
                        }
                        RowLayout {
                            spacing: 6
                            Button { text: "Vídeo…"; onClicked: videoDialog.open() }
                            Button { text: "Imágenes…"; onClicked: imagesDialog.open() }
                            Button { text: "Carpeta…"; onClicked: folderDialog.open() }
                        }

                        Heading { text: "1 · FOTOGRAMA DEL PASE" }
                        Note {
                            text: page.source && page.source.kind === "image" ? "La imagen tiene que ser el instante en que se juega el balón."
                                  : "Busca el instante en que se juega el balón (←/→ un fotograma, Mayús para 10) y calibra ese fotograma."
                        }
                        Button {
                            Layout.fillWidth: true
                            text: page.source && page.source.kind === "image" ? "Calibrar y detectar la imagen"
                                                                              : "Calibrar y detectar el fotograma " + page.number
                            highlighted: true
                            enabled: page.source !== null && !page.backend.busy
                            onClicked: page.prepare()
                        }
                        RowLayout {
                            visible: page.backend.busy
                            spacing: 8
                            BusyIndicator { running: page.backend.busy; implicitWidth: 28; implicitHeight: 28 }
                            Note { text: page.backend.status !== "" ? page.backend.status : "Trabajando…" }
                        }
                        Note {
                            visible: page.prep !== null && page.prepIndex !== page.index
                            color: "#ffd60a"
                            text: "Estás viendo otro fotograma: el análisis es del " + (page.prep ? page.prep.number : "")
                                  + ". Vuelve a él o calibra este."
                        }

                        Heading { text: "2 · CALIBRACIÓN"; visible: page.prep !== null }
                        Note {
                            visible: page.prep !== null
                            color: !page.calibrated ? "#ff6961" : page.prep.calibration.dubious ? "#ffd60a" : "#30d158"
                            text: page.prep ? page.prep.calibration.message : ""
                        }
                        CheckBox {
                            visible: page.calibrated
                            text: "Líneas del campo proyectadas"
                            checked: page.showLines
                            onToggled: { page.showLines = checked; linesCanvas.requestPaint() }
                        }
                        PitchMinimap {
                            id: minimap
                            Layout.fillWidth: true
                            Layout.preferredHeight: implicitHeight
                            visible: page.calibrated
                            calibration: page.prep ? page.prep.calibration : null
                            players: page.prep ? page.prep.players : []
                            teamColors: page.prep ? page.prep.team_colors : []
                            attacker: page.attacker
                            defender: page.defender
                            direction: page.direction
                        }
                        Note {
                            visible: page.calibrated
                            text: "Zona clara: lo que se ve en la imagen. La banda de arriba es la lejana."
                        }

                        Heading { text: "3 · PORTERÍA ATACADA"; visible: page.calibrated }
                        RowLayout {
                            visible: page.calibrated
                            Layout.fillWidth: true
                            spacing: 6
                            Button {
                                Layout.fillWidth: true
                                text: "◀ Izquierda"
                                checkable: true
                                checked: page.direction === -1
                                onClicked: page.setDirection(-1)
                            }
                            Button {
                                Layout.fillWidth: true
                                text: "Derecha ▶"
                                checkable: true
                                checked: page.direction === 1
                                onClicked: page.setDirection(1)
                            }
                        }

                        Heading { text: "4 · JUGADORES"; visible: page.calibrated }
                        Note {
                            visible: page.calibrated
                            text: "Elige qué vas a marcar y haz clic en su caja de la imagen (el balón, en el punto donde está)."
                        }
                        GridLayout {
                            visible: page.calibrated
                            columns: 2
                            columnSpacing: 10
                            rowSpacing: 4
                            Button {
                                text: "Atacante"
                                checkable: true
                                checked: page.pickMode === "attacker"
                                onClicked: page.pickMode = "attacker"
                                Material.accent: "#ff3b30"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: page.attacker > 0 ? "Jugador " + page.attacker : "Sin elegir"
                                color: page.attacker > 0 ? "#ff6961" : "#8e8e93"
                            }
                            Button {
                                text: "Defensor"
                                checkable: true
                                checked: page.pickMode === "defender"
                                onClicked: page.pickMode = "defender"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: page.defender > 0 ? "Jugador " + page.defender : "Sin elegir"
                                color: page.defender > 0 ? "#64a8ff" : "#8e8e93"
                            }
                            Button {
                                text: "Balón"
                                checkable: true
                                checked: page.pickMode === "ball"
                                onClicked: page.pickMode = "ball"
                                Material.accent: "#ff9f0a"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: page.ballMode === "manual" ? "Marcado a mano"
                                      : page.ballMode === "none" ? "Sin balón (no cuenta)"
                                      : page.prep && page.prep.ball ? "Detectado (confianza " + page.prep.ball.conf.toFixed(2) + ")"
                                      : "No detectado"
                                color: page.ballMode === "manual" ? "#ffb340" : "#8e8e93"
                            }
                        }
                        RowLayout {
                            visible: page.calibrated
                            spacing: 6
                            Button {
                                text: "Sin balón"
                                flat: true
                                checkable: true
                                checked: page.ballMode === "none"
                                onClicked: { page.ballMode = "none"; page.result = null }
                            }
                            Button {
                                text: "Automático"
                                flat: true
                                checkable: true
                                checked: page.ballMode === "auto"
                                onClicked: { page.ballMode = "auto"; page.ballPoint = null; page.result = null }
                            }
                        }
                        Note {
                            visible: page.calibrated && page.defenderReason !== ""
                            text: "Penúltimo defensor: " + page.defenderReason.charAt(0).toLowerCase() + page.defenderReason.slice(1)
                        }

                        Button {
                            Layout.fillWidth: true
                            Layout.topMargin: 6
                            visible: page.calibrated
                            text: "Aplicar la Regla 11"
                            highlighted: true
                            enabled: page.ready && !page.backend.busy
                            onClicked: page.analyze()
                        }
                        Note {
                            visible: page.calibrated && !page.ready
                            text: page.direction === 0 ? "Falta la portería atacada." : page.attacker <= 0 ? "Falta el atacante."
                                  : page.defender <= 0 ? "Falta el defensor." : ""
                        }

                        // Result
                        Rectangle {
                            Layout.fillWidth: true
                            visible: page.result !== null
                            readonly property color tone: !page.result ? "#8e8e93" : page.result.within_uncertainty ? "#ffd60a"
                                                          : page.result.status === "offside" ? "#ff3b30"
                                                          : page.result.status === "onside" ? "#30d158" : "#8e8e93"
                            color: Qt.rgba(tone.r, tone.g, tone.b, 0.12)
                            border.color: tone
                            radius: 6
                            implicitHeight: resultColumn.implicitHeight + 20
                            ColumnLayout {
                                id: resultColumn
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 4
                                Label {
                                    text: page.statusText(page.result)
                                    font.pixelSize: 20
                                    font.bold: true
                                    color: parent.parent.tone
                                }
                                Label {
                                    visible: page.result !== null && page.result.margin_m !== null && page.result.margin_m !== undefined
                                    text: page.result ? "Margen " + (page.result.margin_m >= 0 ? "+" : "") + (100 * page.result.margin_m).toFixed(1)
                                                        + " cm · incertidumbre ±" + (100 * page.result.uncertainty_m).toFixed(0) + " cm" : ""
                                }
                                Note {
                                    text: page.result ? "Atacante: " + page.result.attacker_joint + " · línea por "
                                                        + (page.result.line_source === "ball" ? "el balón" : "el defensor (" + page.result.defender_joint + ")") : ""
                                }
                                // Second decision from the image, without the 3D pose
                                Note {
                                    visible: page.result !== null && !!page.result.check_2d
                                    text: page.result && page.result.check_2d
                                          ? "Comprobación 2D (sin la pose 3D): margen "
                                            + (page.result.check_2d.margin_m >= 0 ? "+" : "") + (100 * page.result.check_2d.margin_m).toFixed(1)
                                            + " cm · " + (page.result.check_2d.agrees ? "coincide" : "NO coincide") : ""
                                    color: page.result && page.result.check_2d && !page.result.check_2d.agrees ? "#ffd60a" : "#9aa4ad"
                                }
                                Note {
                                    readonly property var dropped: {
                                        const out = []
                                        const d = page.result ? page.result.discarded_joints : null
                                        if (d)
                                            for (const id in d)
                                                for (const j of d[id])
                                                    out.push("jugador " + id + " " + j)
                                        return out
                                    }
                                    visible: dropped.length > 0
                                    text: "Descartadas por no encajar con el cuerpo: " + dropped.join("; ")
                                }
                                Repeater {
                                    model: page.result ? page.result.warnings : []
                                    delegate: Note {
                                        required property var modelData
                                        text: "⚠ " + modelData
                                        color: "#ffd60a"
                                    }
                                }
                                RowLayout {
                                    spacing: 6
                                    Button {
                                        text: "Ver en 3D"
                                        highlighted: true
                                        onClicked: page.showIn3D(page.result.json)
                                    }
                                    Button {
                                        text: "Imagen del VAR"
                                        checkable: true
                                        checked: page.showVar
                                        onToggled: page.showVar = checked
                                    }
                                }
                            }
                        }

                        Note {
                            visible: page.errorText !== ""
                            color: "#ff6961"
                            text: page.errorText
                        }
                    }
                }
            }
        }
    }
}
