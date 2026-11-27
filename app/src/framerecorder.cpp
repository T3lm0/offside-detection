#include "framerecorder.h"

#include <QDebug>
#include <QImage>

FrameRecorder::FrameRecorder(QObject *parent)
    : QObject(parent)
{
}

FrameRecorder::~FrameRecorder()
{
    if (m_ffmpeg.state() != QProcess::NotRunning)
        finish();
}

void FrameRecorder::setWindow(QQuickWindow *window)
{
    if (window == m_window)
        return;
    m_window = window;
    emit windowChanged();
}

void FrameRecorder::start(const QString &path, int fps, int width, int height)
{
    m_path = path;
    m_fps = fps;
    m_outputSize = QSize(width, height);
    m_frames = 0;
    emit framesChanged();
}

bool FrameRecorder::launchEncoder(const QSize &captureSize)
{
    // ffmpeg receives raw RGBA on stdin; it is scaled to the final size if the window could not get
    // exactly that size (desktop panels)
    m_captureSize = QSize(captureSize.width() & ~1, captureSize.height() & ~1);
    const QStringList args = {
        "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", QStringLiteral("%1x%2").arg(m_captureSize.width()).arg(m_captureSize.height()),
        "-r", QString::number(m_fps), "-i", "-",
        "-vf", QStringLiteral("scale=%1:%2:flags=lanczos").arg(m_outputSize.width()).arg(m_outputSize.height()),
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", m_path,
    };
    m_ffmpeg.setProcessChannelMode(QProcess::ForwardedErrorChannel);
    m_ffmpeg.start("ffmpeg", args);
    if (!m_ffmpeg.waitForStarted()) {
        qWarning() << "No se pudo arrancar ffmpeg";
        return false;
    }
    return true;
}

bool FrameRecorder::capture()
{
    if (!m_window)
        return false;
    return write(m_window->grabWindow());
}

bool FrameRecorder::writeImage(const QVariant &image)
{
    return write(image.value<QImage>());
}

bool FrameRecorder::write(QImage image)
{
    if (image.isNull() || m_path.isEmpty())
        return false;
    if (m_ffmpeg.state() == QProcess::NotRunning && !launchEncoder(image.size()))
        return false;
    image = image.convertToFormat(QImage::Format_RGBA8888).copy(0, 0, m_captureSize.width(), m_captureSize.height());
    m_ffmpeg.write(reinterpret_cast<const char *>(image.constBits()), image.sizeInBytes());
    m_ffmpeg.waitForBytesWritten(-1);
    ++m_frames;
    emit framesChanged();
    return true;
}

bool FrameRecorder::finish()
{
    if (m_ffmpeg.state() == QProcess::NotRunning)
        return false;
    m_ffmpeg.closeWriteChannel();
    m_ffmpeg.waitForFinished(-1);
    const bool ok = m_ffmpeg.exitStatus() == QProcess::NormalExit && m_ffmpeg.exitCode() == 0;
    qInfo().noquote() << QStringLiteral("Vídeo %1: %2 fotogramas (%3 s) en %4")
                             .arg(ok ? "terminado" : "con errores")
                             .arg(m_frames)
                             .arg(double(m_frames) / m_fps, 0, 'f', 1)
                             .arg(m_path);
    return ok;
}
