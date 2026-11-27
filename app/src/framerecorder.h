#pragma once

#include <QObject>
#include <QPointer>
#include <QProcess>
#include <QQuickWindow>
#include <QSize>
#include <QtQml/qqmlregistration.h>

// Records the window frame by frame: each capture() renders the scene as it is at that moment and
// sends it to ffmpeg (H.264). Since it does not depend on real time, the video is smooth even if
// rendering is slow.
class FrameRecorder : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QQuickWindow *window READ window WRITE setWindow NOTIFY windowChanged)
    Q_PROPERTY(int frames READ frames NOTIFY framesChanged)

public:
    explicit FrameRecorder(QObject *parent = nullptr);
    ~FrameRecorder() override;

    QQuickWindow *window() const { return m_window; }
    void setWindow(QQuickWindow *window);
    int frames() const { return m_frames; }

    // Output .mp4, frames per second and final video size
    Q_INVOKABLE void start(const QString &path, int fps, int width = 1920, int height = 1080);
    Q_INVOKABLE bool capture();
    // Adds an already rendered image (e.g. the result of Item.grabToImage), at any size
    Q_INVOKABLE bool writeImage(const QVariant &image);
    Q_INVOKABLE bool finish();

signals:
    void windowChanged();
    void framesChanged();

private:
    bool launchEncoder(const QSize &captureSize);
    bool write(QImage image);

    QPointer<QQuickWindow> m_window;
    QProcess m_ffmpeg;
    QString m_path;
    int m_fps = 30;
    QSize m_outputSize{1920, 1080};
    QSize m_captureSize;
    int m_frames = 0;
};
