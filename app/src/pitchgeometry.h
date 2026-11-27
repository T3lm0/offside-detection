#pragma once

#include <QVector2D>
#include <QtQml/qqmlregistration.h>
#include <QtQuick3D/qquick3dgeometry.h>

// Mesh with every regulation pitch marking (lines, centre circle, areas, penalty spots, arcs and
// corners) as flat strips on the grass.
class PitchLinesGeometry : public QQuick3DGeometry
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(double pitchLength READ pitchLength WRITE setPitchLength NOTIFY geometryParametersChanged)
    Q_PROPERTY(double pitchWidth READ pitchWidth WRITE setPitchWidth NOTIFY geometryParametersChanged)
    Q_PROPERTY(double lineWidth READ lineWidth WRITE setLineWidth NOTIFY geometryParametersChanged)

public:
    explicit PitchLinesGeometry(QQuick3DObject *parent = nullptr);

    double pitchLength() const { return m_length; }
    void setPitchLength(double length);
    double pitchWidth() const { return m_width; }
    void setPitchWidth(double width);
    double lineWidth() const { return m_lineWidth; }
    void setLineWidth(double width);

signals:
    void geometryParametersChanged();

private:
    void rebuild();
    void addQuad(const QVector2D &a, const QVector2D &b, const QVector2D &c, const QVector2D &d);
    void addSegment(const QVector2D &from, const QVector2D &to);
    void addPolyline(const QVector<QVector2D> &points);
    void addArc(const QVector2D &center, float radius, float fromDeg, float toDeg);
    void addDisk(const QVector2D &center, float radius);

    double m_length = 105.0;
    double m_width = 68.0;
    double m_lineWidth = 0.12;
    QVector<float> m_vertices;
};
