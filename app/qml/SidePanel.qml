import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts
import OffsideViewer

// Side panel: plays, decision details, visible layers and analysis data.
Pane {
    id: panel

    required property SceneController controller
    required property QtObject layers

    readonly property var info: controller.eventInfo
    readonly property bool hasEvent: info.valid === true

    padding: 0
    Material.elevation: 4

    component SectionTitle: Label {
        Layout.fillWidth: true
        Layout.topMargin: 14
        font.pixelSize: 12
        font.bold: true
        font.capitalization: Font.AllUppercase
        color: Material.accent
    }
    component Key: Label {
        color: "#a0a7ad"
        Layout.alignment: Qt.AlignTop
    }
    component Value: Label {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
    }
    component LayerCheck: CheckBox {
        property string layerName
        Layout.fillWidth: true
        topPadding: 2
        bottomPadding: 2
        checked: panel.layers[layerName]
        onToggled: panel.layers[layerName] = checked
    }

    function signed(value) {
        return (value > 0 ? "+" : "") + value.toFixed(1)
    }

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 4

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 14
                spacing: 4

                SectionTitle { text: "Jugadas"; Layout.topMargin: 0 }
                Label {
                    visible: panel.controller.events.length === 0
                    text: panel.controller.loaded ? "El análisis no contiene jugadas evaluadas." : "Sin análisis cargado."
                    color: "#a0a7ad"
                }
                Repeater {
                    model: panel.controller.events
                    delegate: ItemDelegate {
                        required property var modelData
                        Layout.fillWidth: true
                        highlighted: modelData.index === panel.controller.selectedEvent
                        onClicked: panel.controller.goToEvent(modelData.index)
                        contentItem: RowLayout {
                            spacing: 8
                            Rectangle {
                                width: 10; height: 10; radius: 5
                                color: modelData.status === "offside" ? "#ff453a"
                                     : modelData.status === "onside" ? "#30d158" : "#8e8e93"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "Pase a " + modelData.receiver + "\nfotograma " + modelData.frame
                                      + " · " + modelData.statusText.toLowerCase()
                                      + " (" + panel.signed(modelData.marginCm) + " cm)"
                                elide: Text.ElideRight
                            }
                        }
                    }
                }

                SectionTitle { text: "Decisión"; visible: panel.hasEvent }
                GridLayout {
                    visible: panel.hasEvent
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 5

                    Key { text: "Estado" }
                    Value {
                        text: panel.hasEvent ? panel.info.statusText : ""
                        font.bold: true
                        color: panel.info.status === "offside" ? "#ff6961" : panel.info.status === "onside" ? "#4cd964" : "white"
                    }
                    Key { text: "Margen" }
                    Value { text: panel.hasEvent ? panel.signed(panel.info.marginCm) + " cm (±" + panel.info.uncertaintyCm.toFixed(0) + " cm)" : "" }
                    Key { text: "Pasador" }
                    Value { text: panel.hasEvent ? panel.info.passer : "" }
                    Key { text: "Atacante" }
                    Value { text: panel.hasEvent ? panel.info.attacker + "\n" + panel.info.attackerJoint : "" }
                    Key { text: "Defensor" }
                    Value { text: panel.hasEvent ? panel.info.defender + "\n" + panel.info.defenderJoint : "" }
                    Key { text: "Línea por" }
                    Value { text: panel.hasEvent ? panel.info.lineSource : "" }
                    Key { text: "Fotograma" }
                    Value { text: panel.hasEvent ? panel.info.frame + "  (" + panel.info.time.toFixed(2) + " s)" : "" }
                }
                Label {
                    visible: panel.hasEvent && panel.info.method !== ""
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    text: panel.hasEvent ? panel.info.method : ""
                    wrapMode: Text.WordWrap
                    color: "#a0a7ad"
                    font.pixelSize: 12
                }
                Repeater {
                    model: panel.hasEvent ? panel.info.warnings : []
                    delegate: Label {
                        required property string modelData
                        Layout.fillWidth: true
                        text: "⚠ " + modelData
                        wrapMode: Text.WordWrap
                        color: "#ffd60a"
                        font.pixelSize: 12
                    }
                }

                SectionTitle { text: "Capas" }
                LayerCheck { text: "Esqueletos"; layerName: "skeletons" }
                LayerCheck { text: "Articulaciones de baja confianza"; layerName: "lowConfidence" }
                LayerCheck { text: "Dorsales"; layerName: "labels" }
                LayerCheck { text: "Balón y estela"; layerName: "ball" }
                LayerCheck { text: "Líneas de fuera de juego"; layerName: "offsideLines" }
                LayerCheck { text: "Planos verticales de las líneas"; layerName: "walls" }
                LayerCheck { text: "Banda de incertidumbre"; layerName: "uncertainty" }
                LayerCheck { text: "Resaltar jugadores de la jugada"; layerName: "highlights" }
                LayerCheck { text: "Sombras"; layerName: "shadows" }
                CheckBox {
                    Layout.fillWidth: true
                    topPadding: 2
                    bottomPadding: 2
                    text: "Oscurecer brazos (no cuentan)"
                    checked: panel.controller.dimInvalidParts
                    onToggled: panel.controller.dimInvalidParts = checked
                }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Confianza mínima"; color: "#a0a7ad" }
                    Slider {
                        id: thresholdSlider
                        Layout.fillWidth: true
                        from: 0
                        to: 0.95
                        stepSize: 0.05
                        value: panel.controller.lowConfidenceThreshold
                        onMoved: panel.controller.lowConfidenceThreshold = value
                    }
                    Label { text: thresholdSlider.value.toFixed(2); font.family: "monospace" }
                }

                SectionTitle { text: "Datos del análisis"; visible: panel.controller.loaded }
                GridLayout {
                    visible: panel.controller.loaded
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 5
                    readonly property var s: panel.controller.stats

                    Key { text: "Entidades" }
                    Value { text: parent.s.players + " jugadores, " + parent.s.goalkeepers + " porteros, " + parent.s.referees + " árbitros" }
                    Key { text: "Secuencia" }
                    Value { text: parent.s.frames + " fotogramas · " + Number(parent.s.duration).toFixed(1) + " s a " + parent.s.fps + " fps" }
                    Key { text: "Con pose 3D" }
                    Value { text: Number(parent.s.poseCoverage).toFixed(1) + " % de las detecciones" }
                    Key { text: "Confianza media" }
                    Value { text: Number(parent.s.meanJointConfidence).toFixed(2) }
                    Key { text: "Balón visible" }
                    Value { text: Number(parent.s.ballCoverage).toFixed(1) + " % de los fotogramas" }
                    Key { text: "Esqueleto" }
                    Value { text: parent.s.skeleton || "" }
                }
            }
        }
    }
}
