#pragma once

#include <QPointer>
#include <QtQml/qqmlregistration.h>
#include <QtQuick3D/qquick3dinstancing.h>

class SceneController;

// Instance table to draw every skeleton with a single Model per part: joints (#Sphere), bones
// (#Cylinder), heads (#Sphere), markers for players without a pose (#Cylinder) and contact shadows
// (flattened #Sphere).
//
// Each part is split into two tables by confidence, so unreliable parts are drawn translucent with
// their own material.
class SkeletonInstancing : public QQuick3DInstancing
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(SceneController *controller READ controller WRITE setController NOTIFY controllerChanged)
    Q_PROPERTY(Part part READ part WRITE setPart NOTIFY partChanged)
    Q_PROPERTY(bool lowConfidence READ lowConfidence WRITE setLowConfidence NOTIFY lowConfidenceChanged)

public:
    enum Part { Joints, Bones, Heads, GroundMarkers, Shadows };
    Q_ENUM(Part)

    explicit SkeletonInstancing(QQuick3DObject *parent = nullptr);

    SceneController *controller() const { return m_controller; }
    void setController(SceneController *controller);
    Part part() const { return m_part; }
    void setPart(Part part);
    bool lowConfidence() const { return m_lowConfidence; }
    void setLowConfidence(bool low);

signals:
    void controllerChanged();
    void partChanged();
    void lowConfidenceChanged();

protected:
    QByteArray getInstanceBuffer(int *instanceCount) override;

private:
    QPointer<SceneController> m_controller;
    Part m_part = Joints;
    bool m_lowConfidence = false;
};
