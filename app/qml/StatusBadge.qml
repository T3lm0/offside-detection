import QtQuick

// Result of the selected play, over the 3D view.
Rectangle {
    id: badge

    required property var info

    readonly property bool valid: info.valid === true
    // Amber if the margin falls within the uncertainty, even if its sign indicates a decision
    readonly property color statusColor: !valid ? "#8e8e93"
                                        : info.withinUncertainty ? "#ffb340"
                                        : info.status === "offside" ? "#ff453a"
                                        : info.status === "onside" ? "#30d158" : "#8e8e93"

    visible: valid
    color: Qt.rgba(0.05, 0.07, 0.09, 0.86)
    radius: 8
    border.color: Qt.rgba(statusColor.r, statusColor.g, statusColor.b, 0.6)
    implicitWidth: column.implicitWidth + 28
    implicitHeight: column.implicitHeight + 20

    function signed(value) {
        return (value > 0 ? "+" : "") + value.toFixed(1)
    }

    Column {
        id: column
        anchors.centerIn: parent
        spacing: 4

        Row {
            spacing: 8
            Rectangle {
                width: 12; height: 12; radius: 6
                color: badge.statusColor
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: !badge.valid ? ""
                      : badge.info.statusText.toUpperCase() + (badge.info.withinUncertainty ? " (NO CONCLUYENTE)" : "")
                color: badge.statusColor
                font.pixelSize: 21
                font.bold: true
            }
        }
        Text {
            text: badge.valid ? "Margen " + badge.signed(badge.info.marginCm) + " cm  ·  incertidumbre ±"
                                + badge.info.uncertaintyCm.toFixed(0) + " cm" : ""
            color: "#e5e5ea"
            font.pixelSize: 13
        }
        Text {
            visible: badge.valid && badge.info.withinUncertainty
            text: "⚠ El margen es menor que la incertidumbre: no concluyente"
            color: "#ffd60a"
            font.pixelSize: 12
        }
        Text {
            text: badge.valid ? "Pase en el fotograma " + badge.info.frame + "  ·  línea por el " + badge.info.lineSource : ""
            color: "#aeaeb2"
            font.pixelSize: 12
        }
    }
}
