#pragma once

#include <QColor>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QVector2D>
#include <QVector3D>

// Result of analysing a play, as written by the Python pipeline ("offside-analysis" format,
// described in docs/analysis_format.md). Coordinates are in metres in the pitch frame: X along,
// Y across, Z up, origin at the centre spot.

struct Skeleton {
    struct Bone {
        int a = -1;
        int b = -1;
        float radius = 0.04f;
    };

    QString name;
    QStringList joints;
    QVector<float> jointRadius;
    QVector<bool> offsideValid; // parts a goal can be scored with (arms excluded)
    QVector<Bone> bones;
    int headA = -1; // the head is drawn as a sphere centred between these two joints
    int headB = -1;
    float headRadius = 0.11f;

    int jointCount() const { return joints.size(); }
};

struct Team {
    QString id;
    QString name;
    QColor color;
    QColor goalkeeperColor;
    int attackDirection = 0; // +1 attacks towards +X, -1 towards -X, 0 no direction (referees)
};

struct Entity {
    int id = -1;
    int team = -1; // index into AnalysisData::teams
    QString role; // player, goalkeeper, referee
    QString number;
    QString name;
};

struct PlayerSample {
    int entity = -1; // index into AnalysisData::entities
    QVector2D ground;
    float confidence = 0.f;
    int poseOffset = -1; // first float of the pose in AnalysisData::poseData; -1 if only the position is known
};

struct FrameSample {
    int frame = 0;
    double time = 0.0;
    QVector<PlayerSample> players;
    QVector<int> slotByEntity; // entity index -> position in players, -1 if absent
    bool hasBall = false;
    QVector3D ball;
    float ballConfidence = 0.f;
};

struct KeyPoint {
    bool valid = false;
    int entity = -1;
    QString joint;
    QVector3D point;
};

struct OffsideCheck {
    bool present = false;
    QString status; // offside, onside, not_evaluable
    bool withinUncertainty = false;
    float marginM = 0.f;
    float uncertaintyM = 0.f;
    float lineX = 0.f;
    QString lineSource; // second_last_defender, ball
    float ballX = 0.f;
    KeyPoint attacker;
    KeyPoint defender;
    QString method;
    QStringList warnings;
};

struct PlayEvent {
    QString id;
    QString type;
    int frame = 0; // video frame number
    int frameIndex = 0; // position in AnalysisData::frames
    double time = 0.0;
    int passer = -1; // entity indices
    int receiver = -1;
    int attackingTeam = -1;
    OffsideCheck offside;
};

class AnalysisData
{
public:
    bool load(const QString &path, QString *error);

    int entityIndex(int id) const;
    QColor entityColor(int entity) const;
    QString entityLabel(int entity) const;

    QString path;
    QString title;
    QString sourceType; // synthetic, pipeline...
    double fps = 25.0;
    float pitchLength = 105.f;
    float pitchWidth = 68.f;
    Skeleton skeleton;
    QVector<Team> teams;
    QVector<Entity> entities;
    QVector<FrameSample> frames;
    QVector<float> poseData; // x, y, z, confidence per joint
    QVector<PlayEvent> events;
};
