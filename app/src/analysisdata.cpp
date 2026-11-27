#include "analysisdata.h"

#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

#include <cmath>
#include <limits>

namespace {

bool fail(QString *error, const QString &message)
{
    if (error)
        *error = message;
    return false;
}

QVector3D readVector3(const QJsonValue &value)
{
    const QJsonArray a = value.toArray();
    return QVector3D(float(a.at(0).toDouble()), float(a.at(1).toDouble()), float(a.at(2).toDouble()));
}

// Joints may be given by index or by name
int jointIndex(const QJsonValue &value, const QStringList &joints)
{
    if (value.isString())
        return joints.indexOf(value.toString());
    const int index = value.toInt(-1);
    return index >= 0 && index < joints.size() ? index : -1;
}

} // namespace

bool AnalysisData::load(const QString &filePath, QString *error)
{
    QFile file(filePath);
    if (!file.open(QIODevice::ReadOnly))
        return fail(error, QStringLiteral("No se puede abrir %1: %2").arg(filePath, file.errorString()));

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (doc.isNull())
        return fail(error, QStringLiteral("JSON no válido (posición %1): %2")
                               .arg(parseError.offset)
                               .arg(parseError.errorString()));

    const QJsonObject root = doc.object();
    if (root.value("format").toString() != QLatin1String("offside-analysis"))
        return fail(error, QStringLiteral("El archivo no tiene el formato \"offside-analysis\""));

    *this = AnalysisData();
    path = filePath;
    title = root.value("match").toObject().value("name").toString(QFileInfo(filePath).completeBaseName());
    sourceType = root.value("source").toObject().value("type").toString("pipeline");
    fps = root.value("sequence").toObject().value("fps").toDouble(25.0);
    const QJsonObject pitch = root.value("pitch").toObject();
    pitchLength = float(pitch.value("length").toDouble(105.0));
    pitchWidth = float(pitch.value("width").toDouble(68.0));

    // Skeleton
    const QJsonObject sk = root.value("skeleton").toObject();
    skeleton.name = sk.value("name").toString();
    for (const QJsonValue &v : sk.value("joints").toArray())
        skeleton.joints.append(v.toString());
    const int jointCount = skeleton.jointCount();
    if (jointCount == 0)
        return fail(error, QStringLiteral("El esqueleto no define articulaciones"));

    const QJsonArray radius = sk.value("joint_radius").toArray();
    const QJsonArray valid = sk.value("offside_valid").toArray();
    for (int j = 0; j < jointCount; ++j) {
        skeleton.jointRadius.append(j < radius.size() ? float(radius.at(j).toDouble()) : 0.04f);
        skeleton.offsideValid.append(j < valid.size() ? valid.at(j).toBool() : true);
    }
    for (const QJsonValue &v : sk.value("bones").toArray()) {
        const QJsonArray b = v.toArray();
        Skeleton::Bone bone;
        bone.a = jointIndex(b.at(0), skeleton.joints);
        bone.b = jointIndex(b.at(1), skeleton.joints);
        bone.radius = float(b.at(2).toDouble(0.04));
        if (bone.a >= 0 && bone.b >= 0)
            skeleton.bones.append(bone);
    }
    const QJsonObject head = sk.value("head").toObject();
    if (!head.isEmpty()) {
        const QJsonArray hj = head.value("joints").toArray();
        skeleton.headA = jointIndex(hj.at(0), skeleton.joints);
        skeleton.headB = jointIndex(hj.at(1), skeleton.joints);
        skeleton.headRadius = float(head.value("radius").toDouble(0.11));
    }

    // Teams and entities
    QHash<QString, int> teamIndex;
    for (const QJsonValue &v : root.value("teams").toArray()) {
        const QJsonObject t = v.toObject();
        Team team;
        team.id = t.value("id").toString();
        team.name = t.value("name").toString(team.id);
        team.color = QColor(t.value("color").toString("#cccccc"));
        team.goalkeeperColor = QColor(t.value("goalkeeper_color").toString(t.value("color").toString("#cccccc")));
        team.attackDirection = t.value("attack_direction").toInt(0);
        teamIndex.insert(team.id, teams.size());
        teams.append(team);
    }
    QHash<int, int> entityById;
    for (const QJsonValue &v : root.value("entities").toArray()) {
        const QJsonObject e = v.toObject();
        Entity entity;
        entity.id = e.value("id").toInt(-1);
        entity.team = teamIndex.value(e.value("team").toString(), -1);
        entity.role = e.value("role").toString("player");
        entity.number = e.value("number").toString();
        entity.name = e.value("name").toString();
        entityById.insert(entity.id, entities.size());
        entities.append(entity);
    }

    // Frames
    const QJsonArray frameArray = root.value("frames").toArray();
    if (frameArray.isEmpty())
        return fail(error, QStringLiteral("El archivo no contiene fotogramas"));
    frames.reserve(frameArray.size());
    poseData.reserve(frameArray.size() * entities.size() * jointCount * 4);
    const float nan = std::numeric_limits<float>::quiet_NaN();

    for (const QJsonValue &fv : frameArray) {
        const QJsonObject fo = fv.toObject();
        FrameSample frame;
        frame.frame = fo.value("frame").toInt(frames.size());
        frame.time = fo.value("time").toDouble(frame.frame / fps);
        frame.slotByEntity.fill(-1, entities.size());

        for (const QJsonValue &pv : fo.value("players").toArray()) {
            const QJsonObject po = pv.toObject();
            PlayerSample sample;
            sample.entity = entityById.value(po.value("id").toInt(), -1);
            if (sample.entity < 0)
                continue;
            const QJsonArray ground = po.value("position").toArray();
            sample.ground = QVector2D(float(ground.at(0).toDouble()), float(ground.at(1).toDouble()));
            sample.confidence = float(po.value("confidence").toDouble(1.0));

            const QJsonArray pose = po.value("pose").toArray();
            if (pose.size() == jointCount) {
                sample.poseOffset = poseData.size();
                for (const QJsonValue &jv : pose) {
                    const QJsonArray j = jv.toArray();
                    if (j.size() >= 3) {
                        poseData << float(j.at(0).toDouble()) << float(j.at(1).toDouble())
                                 << float(j.at(2).toDouble()) << float(j.at(3).toDouble(1.0));
                    } else {
                        // Joint not estimated in this frame
                        poseData << nan << nan << nan << 0.f;
                    }
                }
            }
            frame.slotByEntity[sample.entity] = frame.players.size();
            frame.players.append(sample);
        }

        const QJsonObject ball = fo.value("ball").toObject();
        if (!ball.isEmpty()) {
            frame.hasBall = true;
            frame.ball = readVector3(ball.value("position"));
            frame.ballConfidence = float(ball.value("confidence").toDouble(1.0));
        }
        frames.append(frame);
    }

    // Events (passes and their offside evaluation)
    for (const QJsonValue &v : root.value("events").toArray()) {
        const QJsonObject eo = v.toObject();
        PlayEvent event;
        event.id = eo.value("id").toString();
        event.type = eo.value("type").toString("pass");
        event.frame = eo.value("frame").toInt();
        event.passer = entityById.value(eo.value("passer").toInt(-1), -1);
        event.receiver = entityById.value(eo.value("receiver").toInt(-1), -1);
        event.attackingTeam = teamIndex.value(eo.value("attacking_team").toString(), -1);
        event.frameIndex = 0;
        for (int i = 0; i < frames.size(); ++i) {
            if (frames[i].frame <= event.frame)
                event.frameIndex = i;
        }
        event.time = eo.value("time").toDouble(frames[event.frameIndex].time);

        const QJsonObject oo = eo.value("offside").toObject();
        OffsideCheck &check = event.offside;
        check.present = !oo.isEmpty();
        check.status = oo.value("status").toString("not_evaluable");
        check.withinUncertainty = oo.value("within_uncertainty").toBool();
        check.marginM = float(oo.value("margin_m").toDouble(std::nan("")));
        check.uncertaintyM = float(oo.value("uncertainty_m").toDouble());
        check.lineX = float(oo.value("line").toObject().value("x").toDouble(std::nan("")));
        check.lineSource = oo.value("line").toObject().value("source").toString();
        check.ballX = float(oo.value("ball_x").toDouble(std::nan("")));
        check.method = oo.value("method").toString();
        for (const QJsonValue &w : oo.value("warnings").toArray())
            check.warnings.append(w.toString());
        for (auto [key, point] : {std::pair{"attacker", &check.attacker}, std::pair{"defender", &check.defender}}) {
            const QJsonObject ko = oo.value(QLatin1String(key)).toObject();
            if (ko.isEmpty())
                continue;
            point->valid = ko.contains("point");
            point->entity = entityById.value(ko.value("id").toInt(-1), -1);
            point->joint = ko.value("joint").toString();
            point->point = readVector3(ko.value("point"));
        }
        events.append(event);
    }
    return true;
}

int AnalysisData::entityIndex(int id) const
{
    for (int i = 0; i < entities.size(); ++i) {
        if (entities[i].id == id)
            return i;
    }
    return -1;
}

QColor AnalysisData::entityColor(int entity) const
{
    if (entity < 0 || entity >= entities.size() || entities[entity].team < 0)
        return QColor("#bbbbbb");
    const Team &team = teams[entities[entity].team];
    return entities[entity].role == QLatin1String("goalkeeper") ? team.goalkeeperColor : team.color;
}

QString AnalysisData::entityLabel(int entity) const
{
    if (entity < 0 || entity >= entities.size())
        return QStringLiteral("—");
    const Entity &e = entities[entity];
    const QString team = e.team >= 0 ? teams[e.team].name : QString();
    QString label = e.name.isEmpty() ? QStringLiteral("#%1").arg(e.number) : e.name;
    if (e.role == QLatin1String("referee"))
        label = e.number.isEmpty() ? QStringLiteral("Árbitro") : e.number;
    return team.isEmpty() || e.role == QLatin1String("referee") ? label : QStringLiteral("%1 (%2)").arg(label, team);
}
