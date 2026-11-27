#pragma once

#include "analysisdata.h"

#include <QElapsedTimer>
#include <QObject>
#include <QTimer>
#include <QUrl>
#include <QVariantList>
#include <QVariantMap>
#include <QVector3D>
#include <QVector4D>
#include <QtQml/qqmlregistration.h>

// Scene state at the current instant, already in 3D scene coordinates.
struct RenderPlayer {
    int entity = -1;
    bool hasPose = false;
    QVector3D ground;
    float confidence = 0.f;
    QVector<QVector4D> joints; // scene position + confidence (0 = not estimated)
};

// Loads an analysis, controls playback and interpolates the state between frames so slow motion is
// smooth. Exposes to QML everything the scene needs.
//
// Scene: 1 unit = 1 cm, Y up. Pitch (x, y, z) in metres -> scene (100x, 100z, -100y).
class SceneController : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QUrl source READ source WRITE setSource NOTIFY sourceChanged)
    Q_PROPERTY(bool loaded READ loaded NOTIFY dataChanged)
    Q_PROPERTY(QString errorString READ errorString NOTIFY sourceChanged)
    Q_PROPERTY(QString title READ title NOTIFY dataChanged)
    Q_PROPERTY(bool synthetic READ synthetic NOTIFY dataChanged)
    Q_PROPERTY(int frameCount READ frameCount NOTIFY dataChanged)
    Q_PROPERTY(double fps READ fps NOTIFY dataChanged)
    Q_PROPERTY(double pitchLength READ pitchLength NOTIFY dataChanged)
    Q_PROPERTY(double pitchWidth READ pitchWidth NOTIFY dataChanged)
    Q_PROPERTY(QVariantList events READ events NOTIFY dataChanged)
    Q_PROPERTY(QVariantMap stats READ stats NOTIFY dataChanged)

    Q_PROPERTY(double position READ position WRITE setPosition NOTIFY positionChanged)
    Q_PROPERTY(int frameIndex READ frameIndex NOTIFY positionChanged)
    Q_PROPERTY(int frameNumber READ frameNumber NOTIFY positionChanged)
    Q_PROPERTY(double time READ time NOTIFY positionChanged)
    Q_PROPERTY(bool playing READ playing WRITE setPlaying NOTIFY playingChanged)
    Q_PROPERTY(double playbackRate READ playbackRate WRITE setPlaybackRate NOTIFY playbackRateChanged)

    Q_PROPERTY(int selectedEvent READ selectedEvent WRITE setSelectedEvent NOTIFY selectedEventChanged)
    Q_PROPERTY(QVariantMap eventInfo READ eventInfo NOTIFY selectedEventChanged)

    Q_PROPERTY(QVariantList labels READ labels NOTIFY stateChanged)
    Q_PROPERTY(QVariantList highlights READ highlights NOTIFY stateChanged)
    Q_PROPERTY(bool ballVisible READ ballVisible NOTIFY stateChanged)
    Q_PROPERTY(QVector3D ballPosition READ ballPosition NOTIFY stateChanged)
    Q_PROPERTY(QVariantList ballTrail READ ballTrail NOTIFY stateChanged)

    Q_PROPERTY(bool dimInvalidParts READ dimInvalidParts WRITE setDimInvalidParts NOTIFY renderOptionsChanged)
    Q_PROPERTY(double lowConfidenceThreshold READ lowConfidenceThreshold WRITE setLowConfidenceThreshold
                   NOTIFY renderOptionsChanged)

public:
    explicit SceneController(QObject *parent = nullptr);

    QUrl source() const { return m_source; }
    void setSource(const QUrl &source);
    bool loaded() const { return m_loaded; }
    QString errorString() const { return m_error; }
    QString title() const { return m_data.title; }
    bool synthetic() const { return m_data.sourceType == QLatin1String("synthetic"); }
    int frameCount() const { return m_data.frames.size(); }
    double fps() const { return m_data.fps; }
    double pitchLength() const { return m_data.pitchLength; }
    double pitchWidth() const { return m_data.pitchWidth; }
    QVariantList events() const { return m_events; }
    QVariantMap stats() const { return m_stats; }

    double position() const { return m_position; }
    void setPosition(double position);
    int frameIndex() const;
    int frameNumber() const;
    double time() const;
    bool playing() const { return m_timer.isActive(); }
    void setPlaying(bool playing);
    double playbackRate() const { return m_rate; }
    void setPlaybackRate(double rate);

    int selectedEvent() const { return m_selectedEvent; }
    void setSelectedEvent(int index);
    QVariantMap eventInfo() const { return m_eventInfo; }

    QVariantList labels() const { return m_labels; }
    QVariantList highlights() const { return m_highlights; }
    bool ballVisible() const { return m_ballVisible; }
    QVector3D ballPosition() const { return m_ballPosition; }
    QVariantList ballTrail() const { return m_ballTrail; }

    bool dimInvalidParts() const { return m_dimInvalidParts; }
    void setDimInvalidParts(bool dim);
    double lowConfidenceThreshold() const { return m_lowConfidence; }
    void setLowConfidenceThreshold(double threshold);

    Q_INVOKABLE void togglePlay();
    Q_INVOKABLE void stepFrames(int count);
    Q_INVOKABLE void seekFrameNumber(int frame);
    Q_INVOKABLE void goToEvent(int index);
    Q_INVOKABLE QVector3D toScene(double x, double y, double z) const;
    // Scene position of an entity at the current instant (ground), or (0,0,0)
    Q_INVOKABLE QVector3D entityGround(int entity) const;
    // Entity index from the analysis identifier, or -1
    Q_INVOKABLE int entityIndexForId(int id) const { return m_data.entityIndex(id); }

    // For SkeletonInstancing
    const AnalysisData &data() const { return m_data; }
    const QVector<RenderPlayer> &renderPlayers() const { return m_players; }

signals:
    void sourceChanged();
    void dataChanged();
    void positionChanged();
    void playingChanged();
    void playbackRateChanged();
    void selectedEventChanged();
    void stateChanged();
    void renderOptionsChanged();

private:
    void tick();
    void rebuildState();
    void rebuildEventInfo();
    void rebuildStats();
    QVector3D poseJoint(const PlayerSample &sample, int joint) const;

    AnalysisData m_data;
    QUrl m_source;
    QString m_error;
    bool m_loaded = false;

    double m_position = 0.0;
    double m_rate = 1.0;
    QTimer m_timer;
    QElapsedTimer m_clock;

    int m_selectedEvent = -1;
    QVariantList m_events;
    QVariantMap m_eventInfo;
    QVariantMap m_stats;

    QVector<RenderPlayer> m_players;
    QVariantList m_labels;
    QVariantList m_highlights;
    bool m_ballVisible = false;
    QVector3D m_ballPosition;
    QVariantList m_ballTrail;

    bool m_dimInvalidParts = true;
    double m_lowConfidence = 0.5;
};
