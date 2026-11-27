#include "pitchgeometry.h"

#include <QVector3D>

#include <cmath>

namespace {

constexpr float kSceneScale = 100.f;
constexpr float kLineHeight = 2.f; // units above the grass to avoid z-fighting
constexpr int kFloatsPerVertex = 6; // position + normal

// Regulation dimensions (m)
constexpr float kCenterCircle = 9.15f;
constexpr float kPenaltyDepth = 16.5f;
constexpr float kPenaltyHalfWidth = 20.16f;
constexpr float kGoalAreaDepth = 5.5f;
constexpr float kGoalAreaHalfWidth = 9.16f;
constexpr float kPenaltySpot = 11.f;
constexpr float kSpotRadius = 0.15f;
constexpr float kCornerRadius = 1.f;

} // namespace

PitchLinesGeometry::PitchLinesGeometry(QQuick3DObject *parent)
    : QQuick3DGeometry(parent)
{
    rebuild();
}

void PitchLinesGeometry::setPitchLength(double length)
{
    if (qFuzzyCompare(length, m_length))
        return;
    m_length = length;
    rebuild();
    emit geometryParametersChanged();
}

void PitchLinesGeometry::setPitchWidth(double width)
{
    if (qFuzzyCompare(width, m_width))
        return;
    m_width = width;
    rebuild();
    emit geometryParametersChanged();
}

void PitchLinesGeometry::setLineWidth(double width)
{
    if (qFuzzyCompare(width, m_lineWidth))
        return;
    m_lineWidth = width;
    rebuild();
    emit geometryParametersChanged();
}

void PitchLinesGeometry::addQuad(const QVector2D &a, const QVector2D &b, const QVector2D &c, const QVector2D &d)
{
    // Triangles must wind counter-clockwise seen from above; otherwise the visible face is the back
    // one and it is lit as if facing down
    const QVector2D ab = b - a, ac = c - a;
    if (ab.x() * ac.y() - ab.y() * ac.x() < 0.f) {
        addQuad(a, d, c, b);
        return;
    }
    // Pitch coordinates (x, y) -> scene (x, height, -y), normal pointing up
    for (const QVector2D &p : {a, b, c, a, c, d})
        m_vertices << p.x() * kSceneScale << kLineHeight << -p.y() * kSceneScale << 0.f << 1.f << 0.f;
}

void PitchLinesGeometry::addSegment(const QVector2D &from, const QVector2D &to)
{
    const QVector2D dir = (to - from).normalized();
    const float half = float(m_lineWidth) / 2.f;
    const QVector2D n(-dir.y() * half, dir.x() * half);
    // Each end is extended by half a line width so corners are closed
    const QVector2D a = from - dir * half, b = to + dir * half;
    addQuad(a - n, b - n, b + n, a + n);
}

void PitchLinesGeometry::addPolyline(const QVector<QVector2D> &points)
{
    for (int i = 0; i + 1 < points.size(); ++i)
        addSegment(points[i], points[i + 1]);
}

void PitchLinesGeometry::addArc(const QVector2D &center, float radius, float fromDeg, float toDeg)
{
    const float half = float(m_lineWidth) / 2.f;
    const int steps = std::max(8, int(std::abs(toDeg - fromDeg) / 2.f));
    for (int i = 0; i < steps; ++i) {
        const float a0 = qDegreesToRadians(fromDeg + (toDeg - fromDeg) * i / steps);
        const float a1 = qDegreesToRadians(fromDeg + (toDeg - fromDeg) * (i + 1) / steps);
        const QVector2D d0(std::cos(a0), std::sin(a0)), d1(std::cos(a1), std::sin(a1));
        addQuad(center + d0 * (radius - half), center + d1 * (radius - half), center + d1 * (radius + half),
                center + d0 * (radius + half));
    }
}

void PitchLinesGeometry::addDisk(const QVector2D &center, float radius)
{
    constexpr int steps = 24;
    for (int i = 0; i < steps; ++i) {
        const float a0 = 2.f * float(M_PI) * i / steps, a1 = 2.f * float(M_PI) * (i + 1) / steps;
        const QVector2D p0 = center + QVector2D(std::cos(a0), std::sin(a0)) * radius;
        const QVector2D p1 = center + QVector2D(std::cos(a1), std::sin(a1)) * radius;
        addQuad(center, p0, p1, center);
    }
}

void PitchLinesGeometry::rebuild()
{
    m_vertices.clear();
    const float hl = float(m_length) / 2.f, hw = float(m_width) / 2.f;

    addPolyline({{-hl, -hw}, {hl, -hw}, {hl, hw}, {-hl, hw}, {-hl, -hw}});
    addSegment({0.f, -hw}, {0.f, hw});
    addArc({0.f, 0.f}, kCenterCircle, 0.f, 360.f);
    addDisk({0.f, 0.f}, kSpotRadius);

    // Penalty arc: the part of the 9.15 m circle outside the penalty area
    const float arcHalf = qRadiansToDegrees(std::acos((kPenaltyDepth - kPenaltySpot) / kCenterCircle));
    for (const float s : {-1.f, 1.f}) {
        const float goal = s * hl;
        addPolyline({{goal, -kPenaltyHalfWidth}, {goal - s * kPenaltyDepth, -kPenaltyHalfWidth},
                     {goal - s * kPenaltyDepth, kPenaltyHalfWidth}, {goal, kPenaltyHalfWidth}});
        addPolyline({{goal, -kGoalAreaHalfWidth}, {goal - s * kGoalAreaDepth, -kGoalAreaHalfWidth},
                     {goal - s * kGoalAreaDepth, kGoalAreaHalfWidth}, {goal, kGoalAreaHalfWidth}});
        const QVector2D spot(goal - s * kPenaltySpot, 0.f);
        addDisk(spot, kSpotRadius);
        const float facing = s > 0 ? 180.f : 0.f;
        addArc(spot, kCenterCircle, facing - arcHalf, facing + arcHalf);
        // Corners: quarter circle towards the inside of the pitch
        addArc({goal, -hw}, kCornerRadius, s > 0 ? 90.f : 0.f, s > 0 ? 180.f : 90.f);
        addArc({goal, hw}, kCornerRadius, s > 0 ? 180.f : 270.f, s > 0 ? 270.f : 360.f);
    }

    clear();
    setPrimitiveType(PrimitiveType::Triangles);
    setStride(kFloatsPerVertex * sizeof(float));
    setVertexData(QByteArray(reinterpret_cast<const char *>(m_vertices.constData()),
                             m_vertices.size() * sizeof(float)));
    addAttribute(Attribute::PositionSemantic, 0, Attribute::F32Type);
    addAttribute(Attribute::NormalSemantic, 3 * sizeof(float), Attribute::F32Type);
    setBounds(QVector3D(-(hl + 2) * kSceneScale, 0.f, -(hw + 2) * kSceneScale),
              QVector3D((hl + 2) * kSceneScale, kLineHeight, (hw + 2) * kSceneScale));
    update();
}
