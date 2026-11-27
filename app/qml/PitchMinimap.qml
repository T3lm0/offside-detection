import QtQuick

// Top-down pitch with the far touchline at the top (as in the main camera): the area visible in the
// image, the detected players and the attacked goal. Used to check the calibration and to choose
// which goal is attacked.
Canvas {
    id: map

    property var calibration: null // prepare response
    property var players: []
    property var teamColors: []
    property int attacker: -1
    property int defender: -1
    property int direction: 0 // +1 towards the right (+X), -1 towards the left
    readonly property real margin: 4 // metres around the pitch

    implicitHeight: width * (68 + 2 * margin) / (105 + 2 * margin)

    function px(x) { return (x + 52.5 + margin) / (105 + 2 * margin) * width }
    function py(y) { return (34 + margin - y) / (68 + 2 * margin) * height }

    onCalibrationChanged: requestPaint()
    onPlayersChanged: requestPaint()
    onAttackerChanged: requestPaint()
    onDefenderChanged: requestPaint()
    onDirectionChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        ctx.fillStyle = "#1d4d2b"
        ctx.fillRect(0, 0, width, height)

        // Area visible in the image
        const fp = calibration && calibration.footprint ? calibration.footprint : []
        if (fp.length > 2) {
            ctx.beginPath()
            ctx.moveTo(px(fp[0][0]), py(fp[0][1]))
            for (let i = 1; i < fp.length; ++i)
                ctx.lineTo(px(fp[i][0]), py(fp[i][1]))
            ctx.closePath()
            ctx.fillStyle = Qt.rgba(1, 1, 1, 0.13)
            ctx.fill()
        }

        // Pitch markings
        ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.75)
        ctx.lineWidth = 1
        ctx.strokeRect(px(-52.5), py(34), px(52.5) - px(-52.5), py(-34) - py(34))
        ctx.beginPath(); ctx.moveTo(px(0), py(34)); ctx.lineTo(px(0), py(-34)); ctx.stroke()
        ctx.beginPath(); ctx.ellipse(px(-9.15), py(9.15), px(9.15) - px(-9.15), py(-9.15) - py(9.15)); ctx.stroke()
        for (const s of [-1, 1]) {
            const g = s * 52.5
            ctx.strokeRect(Math.min(px(g), px(g - s * 16.5)), py(20.16), Math.abs(px(g) - px(g - s * 16.5)), py(-20.16) - py(20.16))
            ctx.strokeRect(Math.min(px(g), px(g - s * 5.5)), py(9.16), Math.abs(px(g) - px(g - s * 5.5)), py(-9.16) - py(9.16))
        }

        // Attacked goal
        if (direction !== 0) {
            const g = direction * 52.5
            ctx.fillStyle = "#ff3b30"
            ctx.fillRect(Math.min(px(g), px(g + direction * 2)), py(3.66), Math.abs(px(g + direction * 2) - px(g)), py(-3.66) - py(3.66))
        }

        // Players
        for (const p of players) {
            if (!p.ground)
                continue
            const chosen = p.id === attacker ? "#ff3b30" : p.id === defender ? "#2f8cff" : ""
            let color = p.role === "referee" ? "#ffd60a" : p.role === "goalkeeper" ? "#bf5af2"
                      : (p.team !== null && p.team !== undefined && teamColors[p.team]) ? teamColors[p.team] : "#8e8e93"
            ctx.beginPath()
            ctx.arc(px(p.ground[0]), py(p.ground[1]), chosen ? 5 : 3.5, 0, 2 * Math.PI)
            ctx.fillStyle = color
            ctx.fill()
            ctx.lineWidth = chosen ? 2.5 : 1
            ctx.strokeStyle = chosen ? chosen : "#0e1418"
            ctx.stroke()
        }
    }
}
