#include "scenecontroller.h"

#include <QHash>

#include <algorithm>
#include <cmath>

namespace {

constexpr float kSceneScale = 100.f; // metres -> scene units (cm)
constexpr int kBallTrailFrames = 14;

QVector3D fieldToScene(float x, float y, float z)
{
    return QVector3D(x * kSceneScale, z * kSceneScale, -y * kSceneScale);
}

QString jointDisplayName(const QString &joint)
{
    static const QHash<QString, QString> names = {
        {"nose", "nariz"}, {"left_eye", "ojo izquierdo"}, {"right_eye", "ojo derecho"},
        {"left_ear", "oreja izquierda"}, {"right_ear", "oreja derecha"}, {"head", "cabeza"}, {"neck", "cuello"},
        {"left_shoulder", "hombro izquierdo"}, {"right_shoulder", "hombro derecho"},
        {"left_elbow", "codo izquierdo"}, {"right_elbow", "codo derecho"},
        {"left_wrist", "muñeca izquierda"}, {"right_wrist", "muñeca derecha"}, {"hip", "pelvis"},
        {"left_hip", "cadera izquierda"}, {"right_hip", "cadera derecha"},
        {"left_knee", "rodilla izquierda"}, {"right_knee", "rodilla derecha"},
        {"left_ankle", "tobillo izquierdo"}, {"right_ankle", "tobillo derecho"},
        {"left_big_toe", "punta del pie izquierdo"}, {"right_big_toe", "punta del pie derecho"},
        {"left_small_toe", "dedo pequeño izquierdo"}, {"right_small_toe", "dedo pequeño derecho"},
        {"left_heel", "talón izquierdo"}, {"right_heel", "talón derecho"},
    };
    return names.value(joint, joint);
}

QString statusText(const QString &status)
{
    if (status == QLatin1String("offside"))
        return QStringLiteral("Fuera de juego");
    if (status == QLatin1String("onside"))
        return QStringLiteral("Posición legal");
    return QStringLiteral("No evaluable");
}

} // namespace

SceneController::SceneController(QObject *parent)
    : QObject(parent)
{
    m_timer.setInterval(15);
    m_timer.setTimerType(Qt::PreciseTimer);
    connect(&m_timer, &QTimer::timeout, this, &SceneController::tick);
}

void SceneController::setSource(const QUrl &source)
{
    m_source = source;
    setPlaying(false);
    const QString path = source.isLocalFile() ? source.toLocalFile() : source.toString();
    AnalysisData data;
    QString error;
    if (path.isEmpty() || !data.load(path, &error)) {
        // Keep the previous analysis and report the error
        m_error = path.isEmpty() ? QString() : error;
        emit sourceChanged();
        return;
    }

    m_data = std::move(data);
    m_error.clear();
    m_loaded = true;
    m_position = 0.0;
    m_selectedEvent = m_data.events.isEmpty() ? -1 : 0;

    m_events.clear();
    for (int i = 0; i < m_data.events.size(); ++i) {
        const PlayEvent &e = m_data.events[i];
        m_events.append(QVariantMap{
            {"index", i},
            {"id", e.id},
            {"type", e.type},
            {"frame", e.frame},
            {"frameIndex", e.frameIndex},
            {"time", e.time},
            {"status", e.offside.status},
            {"statusText", statusText(e.offside.status)},
            {"marginCm", e.offside.marginM * 100.0},
            {"withinUncertainty", e.offside.withinUncertainty},
            {"receiver", m_data.entityLabel(e.receiver)},
        });
    }
    rebuildStats();
    rebuildEventInfo();
    rebuildState();
    emit sourceChanged();
    emit dataChanged();
    emit positionChanged();
    emit selectedEventChanged();
}

void SceneController::setPosition(double position)
{
    if (!m_loaded)
        return;
    position = std::clamp(position, 0.0, double(frameCount() - 1));
    if (qFuzzyCompare(position + 1.0, m_position + 1.0))
        return;
    m_position = position;
    rebuildState();
    emit positionChanged();
}

int SceneController::frameIndex() const
{
    return m_loaded ? std::clamp(int(std::lround(m_position)), 0, frameCount() - 1) : 0;
}

int SceneController::frameNumber() const
{
    return m_loaded ? m_data.frames[frameIndex()].frame : 0;
}

double SceneController::time() const
{
    if (!m_loaded)
        return 0.0;
    const int i0 = int(std::floor(m_position));
    const int i1 = std::min(i0 + 1, frameCount() - 1);
    const double t = m_position - i0;
    return m_data.frames[i0].time * (1.0 - t) + m_data.frames[i1].time * t;
}

void SceneController::setPlaying(bool playing)
{
    if (playing == m_timer.isActive() || (playing && !m_loaded))
        return;
    if (playing) {
        if (m_position >= frameCount() - 1)
            setPosition(0.0);
        m_clock.start();
        m_timer.start();
    } else {
        m_timer.stop();
    }
    emit playingChanged();
}

void SceneController::setPlaybackRate(double rate)
{
    rate = std::clamp(rate, 0.05, 4.0);
    if (qFuzzyCompare(rate, m_rate))
        return;
    m_rate = rate;
    emit playbackRateChanged();
}

void SceneController::setSelectedEvent(int index)
{
    if (index < -1 || index >= m_data.events.size() || index == m_selectedEvent)
        return;
    m_selectedEvent = index;
    rebuildEventInfo();
    rebuildState();
    emit selectedEventChanged();
}

void SceneController::setDimInvalidParts(bool dim)
{
    if (dim == m_dimInvalidParts)
        return;
    m_dimInvalidParts = dim;
    emit renderOptionsChanged();
}

void SceneController::setLowConfidenceThreshold(double threshold)
{
    if (qFuzzyCompare(threshold, m_lowConfidence))
        return;
    m_lowConfidence = threshold;
    emit renderOptionsChanged();
}

void SceneController::togglePlay()
{
    setPlaying(!playing());
}

void SceneController::stepFrames(int count)
{
    setPlaying(false);
    setPosition(std::round(m_position) + count);
}

void SceneController::seekFrameNumber(int frame)
{
    for (int i = 0; i < frameCount(); ++i) {
        if (m_data.frames[i].frame >= frame) {
            setPosition(i);
            return;
        }
    }
    setPosition(frameCount() - 1);
}

void SceneController::goToEvent(int index)
{
    if (index < 0 || index >= m_data.events.size())
        return;
    setSelectedEvent(index);
    setPlaying(false);
    setPosition(m_data.events[index].frameIndex);
}

QVector3D SceneController::toScene(double x, double y, double z) const
{
    return fieldToScene(float(x), float(y), float(z));
}

QVector3D SceneController::entityGround(int entity) const
{
    for (const RenderPlayer &p : m_players) {
        if (p.entity == entity)
            return p.ground;
    }
    return QVector3D();
}

void SceneController::tick()
{
    const double dt = m_clock.restart() / 1000.0;
    const double next = m_position + dt * m_data.fps * m_rate;
    if (next >= frameCount() - 1) {
        setPosition(frameCount() - 1);
        setPlaying(false);
        return;
    }
    setPosition(next);
}

QVector3D SceneController::poseJoint(const PlayerSample &sample, int joint) const
{
    const float *p = m_data.poseData.constData() + sample.poseOffset + joint * 4;
    return QVector3D(p[0], p[1], p[2]);
}

void SceneController::rebuildState()
{
    m_players.clear();
    m_labels.clear();
    m_highlights.clear();
    m_ballTrail.clear();
    m_ballVisible = false;
    if (!m_loaded) {
        emit stateChanged();
        return;
    }

    // Linear interpolation between the two frames around the current position
    const int i0 = int(std::floor(m_position));
    const int i1 = std::min(i0 + 1, frameCount() - 1);
    const float t = float(m_position - i0);
    const FrameSample &f0 = m_data.frames[i0];
    const FrameSample &f1 = m_data.frames[i1];
    const int jointCount = m_data.skeleton.jointCount();
    const float *pose = m_data.poseData.constData();

    for (const PlayerSample &a : f0.players) {
        const int slot = f1.slotByEntity.value(a.entity, -1);
        const PlayerSample &b = slot >= 0 ? f1.players[slot] : a;
        RenderPlayer rp;
        rp.entity = a.entity;
        const QVector2D g = a.ground * (1.f - t) + b.ground * t;
        rp.ground = fieldToScene(g.x(), g.y(), 0.f);
        rp.confidence = a.confidence * (1.f - t) + b.confidence * t;
        rp.hasPose = a.poseOffset >= 0;
        if (rp.hasPose) {
            const float *pa = pose + a.poseOffset;
            const float *pb = b.poseOffset >= 0 ? pose + b.poseOffset : pa;
            rp.joints.resize(jointCount);
            for (int j = 0; j < jointCount; ++j) {
                const float *ja = pa + j * 4;
                const float *jb = std::isnan(pb[j * 4]) ? ja : pb + j * 4;
                if (std::isnan(ja[0]) || ja[3] <= 0.f) {
                    rp.joints[j] = QVector4D(0, 0, 0, 0);
                    continue;
                }
                const QVector3D p = fieldToScene(ja[0] + (jb[0] - ja[0]) * t, ja[1] + (jb[1] - ja[1]) * t,
                                                 ja[2] + (jb[2] - ja[2]) * t);
                rp.joints[j] = QVector4D(p, ja[3] + (jb[3] - ja[3]) * t);
            }
        }
        m_players.append(rp);
    }

    // Labels above the head
    const PlayEvent *event = m_selectedEvent >= 0 ? &m_data.events[m_selectedEvent] : nullptr;
    for (const RenderPlayer &p : std::as_const(m_players)) {
        const Entity &e = m_data.entities[p.entity];
        QVector3D anchor = p.ground + QVector3D(0, 215, 0);
        if (p.hasPose) {
            float top = 0.f;
            for (const QVector4D &j : p.joints) {
                if (j.w() > 0.f)
                    top = std::max(top, j.y());
            }
            anchor = QVector3D(p.ground.x(), top + 40.f, p.ground.z());
        }
        const bool key = event && (p.entity == event->passer || p.entity == event->receiver
                                   || p.entity == event->offside.defender.entity);
        m_labels.append(QVariantMap{
            {"entity", p.entity},
            {"text", e.number.isEmpty() ? QStringLiteral("?") : e.number},
            {"color", m_data.entityColor(p.entity)},
            {"position", anchor},
            {"approximate", !p.hasPose},
            {"key", key},
        });
    }

    // Discs under the players of the selected play
    if (event) {
        const QVector<std::pair<int, QColor>> keys = {
            {event->passer, QColor("#ffd60a")},
            {event->receiver, QColor("#ff3b30")},
            {event->offside.defender.entity, QColor("#2979ff")},
        };
        for (const auto &[entity, color] : keys) {
            if (entity < 0)
                continue;
            for (const RenderPlayer &p : std::as_const(m_players)) {
                if (p.entity == entity)
                    m_highlights.append(QVariantMap{{"position", p.ground}, {"color", color}});
            }
        }
    }

    // Ball and its trail
    if (f0.hasBall) {
        m_ballVisible = true;
        const QVector3D b = f1.hasBall ? f0.ball * (1.f - t) + f1.ball * t : f0.ball;
        m_ballPosition = fieldToScene(b.x(), b.y(), b.z());
    }
    for (int k = kBallTrailFrames; k >= 1; --k) {
        const int i = i0 - k;
        if (i < 0 || !m_data.frames[i].hasBall)
            continue;
        const QVector3D b = m_data.frames[i].ball;
        m_ballTrail.append(QVariantMap{
            {"position", fieldToScene(b.x(), b.y(), b.z())},
            {"alpha", 0.55 * (1.0 - double(k) / (kBallTrailFrames + 1))},
        });
    }
    emit stateChanged();
}

void SceneController::rebuildEventInfo()
{
    m_eventInfo.clear();
    if (m_selectedEvent < 0) {
        m_eventInfo.insert("valid", false);
        return;
    }
    const PlayEvent &e = m_data.events[m_selectedEvent];
    const OffsideCheck &o = e.offside;
    const FrameSample &frame = m_data.frames[e.frameIndex];
    const int attackDir = e.attackingTeam >= 0 ? m_data.teams[e.attackingTeam].attackDirection : 1;

    auto groundOf = [&](int entity) {
        const int slot = entity >= 0 ? frame.slotByEntity.value(entity, -1) : -1;
        if (slot < 0)
            return QVector3D();
        const QVector2D g = frame.players[slot].ground;
        return fieldToScene(g.x(), g.y(), 0.f);
    };
    auto keyPoint = [&](const QString &prefix, const KeyPoint &k) {
        m_eventInfo.insert(prefix + "Entity", k.entity);
        m_eventInfo.insert(prefix, m_data.entityLabel(k.entity));
        m_eventInfo.insert(prefix + "Joint", jointDisplayName(k.joint));
        m_eventInfo.insert(prefix + "HasPoint", k.valid);
        const QVector3D p = fieldToScene(k.point.x(), k.point.y(), k.point.z());
        m_eventInfo.insert(prefix + "Point", p);
        m_eventInfo.insert(prefix + "PointGround", QVector3D(p.x(), 0.f, p.z()));
        m_eventInfo.insert(prefix + "X", p.x());
    };

    m_eventInfo.insert("valid", o.present);
    m_eventInfo.insert("type", e.type);
    m_eventInfo.insert("frame", e.frame);
    m_eventInfo.insert("frameIndex", e.frameIndex);
    m_eventInfo.insert("time", e.time);
    m_eventInfo.insert("status", o.status);
    m_eventInfo.insert("statusText", statusText(o.status));
    m_eventInfo.insert("withinUncertainty", o.withinUncertainty);
    m_eventInfo.insert("marginCm", o.marginM * 100.0);
    m_eventInfo.insert("uncertaintyCm", o.uncertaintyM * 100.0);
    m_eventInfo.insert("uncertainty", o.uncertaintyM * kSceneScale);
    m_eventInfo.insert("lineX", o.lineX * kSceneScale);
    m_eventInfo.insert("ballX", o.ballX * kSceneScale);
    m_eventInfo.insert("lineSource", o.lineSource == QLatin1String("ball") ? QStringLiteral("balón")
                                                                            : QStringLiteral("penúltimo defensor"));
    m_eventInfo.insert("lineFromBall", o.lineSource == QLatin1String("ball"));
    m_eventInfo.insert("attackDirection", attackDir);
    m_eventInfo.insert("passer", m_data.entityLabel(e.passer));
    m_eventInfo.insert("passerEntity", e.passer);
    m_eventInfo.insert("receiver", m_data.entityLabel(e.receiver));
    m_eventInfo.insert("receiverEntity", e.receiver);
    m_eventInfo.insert("receiverGround", groundOf(e.receiver));
    keyPoint("attacker", o.attacker);
    keyPoint("defender", o.defender);
    m_eventInfo.insert("method", o.method);
    m_eventInfo.insert("warnings", o.warnings);
}

void SceneController::rebuildStats()
{
    int players = 0, goalkeepers = 0, referees = 0;
    for (const Entity &e : std::as_const(m_data.entities)) {
        if (e.role == QLatin1String("goalkeeper"))
            ++goalkeepers;
        else if (e.role == QLatin1String("referee"))
            ++referees;
        else
            ++players;
    }
    int samples = 0, withPose = 0, framesWithBall = 0, joints = 0;
    double confidence = 0.0;
    for (const FrameSample &f : std::as_const(m_data.frames)) {
        framesWithBall += f.hasBall ? 1 : 0;
        for (const PlayerSample &s : f.players) {
            ++samples;
            if (s.poseOffset < 0)
                continue;
            ++withPose;
            for (int j = 0; j < m_data.skeleton.jointCount(); ++j) {
                const float c = m_data.poseData[s.poseOffset + j * 4 + 3];
                if (c > 0.f) {
                    confidence += c;
                    ++joints;
                }
            }
        }
    }
    const int n = std::max(1, frameCount());
    m_stats = {
        {"players", players},
        {"goalkeepers", goalkeepers},
        {"referees", referees},
        {"frames", frameCount()},
        {"duration", frameCount() / std::max(1.0, m_data.fps)},
        {"fps", m_data.fps},
        {"poseCoverage", samples ? 100.0 * withPose / samples : 0.0},
        {"meanJointConfidence", joints ? confidence / joints : 0.0},
        {"ballCoverage", 100.0 * framesWithBall / n},
        {"events", m_data.events.size()},
        {"skeleton", QStringLiteral("%1 (%2 articulaciones)").arg(m_data.skeleton.name).arg(m_data.skeleton.jointCount())},
    };
}
