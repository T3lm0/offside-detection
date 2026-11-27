import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import OffsideViewer

// Playback: play/pause, step by step, timeline with the marked plays, and speed.
ToolBar {
    id: bar

    required property SceneController controller

    readonly property var rates: [0.1, 0.25, 0.5, 1.0, 2.0]

    function formatTime(seconds) {
        const m = Math.floor(seconds / 60)
        const s = seconds - m * 60
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s.toFixed(2)
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 2
        enabled: bar.controller.loaded

        ToolButton {
            text: "⏮"
            onClicked: bar.controller.goToEvent(bar.controller.selectedEvent)
            ToolTip.visible: hovered
            ToolTip.text: "Ir al pase seleccionado (P)"
        }
        ToolButton {
            text: "◀"
            autoRepeat: true
            onClicked: bar.controller.stepFrames(-1)
            ToolTip.visible: hovered
            ToolTip.text: "Fotograma anterior (←)"
        }
        ToolButton {
            text: bar.controller.playing ? "❚❚" : "▶"
            font.pixelSize: 18
            onClicked: bar.controller.togglePlay()
            ToolTip.visible: hovered
            ToolTip.text: "Reproducir / pausar (espacio)"
        }
        ToolButton {
            text: "▶|"
            autoRepeat: true
            onClicked: bar.controller.stepFrames(1)
            ToolTip.visible: hovered
            ToolTip.text: "Fotograma siguiente (→)"
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: slider.implicitHeight

            Slider {
                id: slider
                anchors.fill: parent
                from: 0
                to: Math.max(1, bar.controller.frameCount - 1)
                value: bar.controller.position
                onMoved: {
                    bar.controller.playing = false
                    bar.controller.position = value
                }
                Connections {
                    target: bar.controller
                    function onPositionChanged() {
                        if (!slider.pressed)
                            slider.value = bar.controller.position
                    }
                }
            }

            // Marks of the analysed plays
            Repeater {
                model: bar.controller.events
                delegate: Rectangle {
                    required property var modelData
                    x: slider.leftPadding + slider.availableWidth * modelData.frameIndex
                       / Math.max(1, bar.controller.frameCount - 1) - width / 2
                    y: slider.topPadding + slider.availableHeight / 2 - height - 6
                    width: 4
                    height: 14
                    radius: 2
                    color: modelData.status === "offside" ? "#ff453a" : modelData.status === "onside" ? "#30d158" : "#8e8e93"
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -4
                        cursorShape: Qt.PointingHandCursor
                        onClicked: bar.controller.goToEvent(parent.modelData.index)
                    }
                }
            }
        }

        Label {
            text: bar.formatTime(bar.controller.time) + "  ·  fotograma " + bar.controller.frameNumber
                  + " (" + (bar.controller.frameIndex + 1) + "/" + bar.controller.frameCount + ")"
            font.family: "monospace"
            Layout.rightMargin: 8
        }
        ComboBox {
            id: rateBox
            model: ["0,1×", "0,25×", "0,5×", "1×", "2×"]
            currentIndex: 3
            implicitWidth: 92
            onActivated: bar.controller.playbackRate = bar.rates[currentIndex]
            ToolTip.visible: hovered
            ToolTip.text: "Velocidad de reproducción"
        }
    }
}
