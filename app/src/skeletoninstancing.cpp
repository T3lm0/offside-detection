#include "skeletoninstancing.h"

#include "scenecontroller.h"

#include <QQuaternion>

#include <algorithm>

namespace {

// Qt Quick 3D primitives are 100 units: sphere and cylinder of radius 50 and cylinder height 100
// (Y axis). Skeleton radii are given in metres.
constexpr float kPrimitiveRadius = 50.f;
constexpr float kSceneScale = 100.f;
constexpr float kLowConfidenceAlpha = 0.32f;

QColor partColor(QColor base, bool lowConfidence, bool dimmed)
{
    if (dimmed)
        base = base.darker(185);
    if (lowConfidence)
        base.setAlphaF(kLowConfidenceAlpha);
    return base;
}

} // namespace

SkeletonInstancing::SkeletonInstancing(QQuick3DObject *parent)
    : QQuick3DInstancing(parent)
{
}

void SkeletonInstancing::setController(SceneController *controller)
{
    if (controller == m_controller)
        return;
    if (m_controller)
        disconnect(m_controller, nullptr, this, nullptr);
    m_controller = controller;
    if (m_controller) {
        connect(m_controller, &SceneController::stateChanged, this, &SkeletonInstancing::markDirty);
        connect(m_controller, &SceneController::renderOptionsChanged, this, &SkeletonInstancing::markDirty);
    }
    markDirty();
    emit controllerChanged();
}

void SkeletonInstancing::setPart(Part part)
{
    if (part == m_part)
        return;
    m_part = part;
    markDirty();
    emit partChanged();
}

void SkeletonInstancing::setLowConfidence(bool low)
{
    if (low == m_lowConfidence)
        return;
    m_lowConfidence = low;
    setHasTransparency(low);
    setDepthSortingEnabled(low);
    markDirty();
    emit lowConfidenceChanged();
}

QByteArray SkeletonInstancing::getInstanceBuffer(int *instanceCount)
{
    QByteArray buffer;
    int count = 0;
    auto add = [&](const InstanceTableEntry &entry) {
        buffer.append(reinterpret_cast<const char *>(&entry), sizeof(entry));
        ++count;
    };

    if (m_controller) {
        const AnalysisData &data = m_controller->data();
        const Skeleton &skeleton = data.skeleton;
        const float threshold = float(m_controller->lowConfidenceThreshold());
        const bool dim = m_controller->dimInvalidParts();
        // A part goes into this table if its confidence falls on the corresponding side
        auto accept = [&](float confidence) {
            return confidence > 0.f && (confidence < threshold) == m_lowConfidence;
        };

        for (const RenderPlayer &p : m_controller->renderPlayers()) {
            const QColor base = data.entityColor(p.entity);
            switch (m_part) {
            case Joints:
                if (!p.hasPose)
                    break;
                for (int j = 0; j < p.joints.size(); ++j) {
                    const QVector4D &joint = p.joints[j];
                    const float radius = skeleton.jointRadius.value(j) * kSceneScale;
                    if (radius <= 0.f || !accept(joint.w()))
                        continue;
                    const QColor color = partColor(base.lighter(135), m_lowConfidence,
                                                   dim && !skeleton.offsideValid.value(j, true));
                    const float s = radius / kPrimitiveRadius;
                    add(calculateTableEntry(joint.toVector3D(), QVector3D(s, s, s), QVector3D(), color));
                }
                break;

            case Bones:
                if (!p.hasPose)
                    break;
                for (const Skeleton::Bone &bone : skeleton.bones) {
                    const QVector4D &a = p.joints[bone.a];
                    const QVector4D &b = p.joints[bone.b];
                    if (!accept(std::min(a.w(), b.w())) || a.w() <= 0.f || b.w() <= 0.f)
                        continue;
                    const QVector3D dir = b.toVector3D() - a.toVector3D();
                    const float length = dir.length();
                    if (length < 0.5f)
                        continue;
                    const bool invalid = !skeleton.offsideValid.value(bone.a, true)
                                         || !skeleton.offsideValid.value(bone.b, true);
                    const QColor color = partColor(base, m_lowConfidence, dim && invalid);
                    const float r = bone.radius * kSceneScale / kPrimitiveRadius;
                    const QQuaternion rotation = QQuaternion::rotationTo(QVector3D(0, 1, 0), dir / length);
                    add(calculateTableEntryFromQuaternion((a.toVector3D() + b.toVector3D()) * 0.5f,
                                                          QVector3D(r, length / 100.f, r), rotation, color));
                }
                break;

            case Heads: {
                if (!p.hasPose || skeleton.headA < 0 || skeleton.headB < 0)
                    break;
                const QVector4D &a = p.joints[skeleton.headA];
                const QVector4D &b = p.joints[skeleton.headB];
                if (a.w() <= 0.f || b.w() <= 0.f || !accept(std::min(a.w(), b.w())))
                    break;
                const float s = skeleton.headRadius * kSceneScale / kPrimitiveRadius;
                add(calculateTableEntry((a.toVector3D() + b.toVector3D()) * 0.5f, QVector3D(s, s, s), QVector3D(),
                                        partColor(base.lighter(120), m_lowConfidence, false)));
                break;
            }

            case GroundMarkers:
                // No estimated pose: only the ground position is known and no pose is made up
                if (p.hasPose || m_lowConfidence)
                    break;
                add(calculateTableEntry(p.ground + QVector3D(0, 90, 0), QVector3D(0.6f, 1.8f, 0.6f), QVector3D(),
                                        partColor(base, true, false)));
                break;

            case Shadows:
                if (m_lowConfidence)
                    break;
                add(calculateTableEntry(p.ground + QVector3D(0, 1.5f, 0), QVector3D(0.95f, 0.004f, 0.95f),
                                        QVector3D(), QColor(0, 0, 0, 90)));
                break;
            }
        }
    }

    if (instanceCount)
        *instanceCount = count;
    return buffer;
}
