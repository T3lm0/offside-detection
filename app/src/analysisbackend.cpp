#include "analysisbackend.h"

#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QtDebug>

#ifndef OFFSIDE_BACKEND_SCRIPT
#define OFFSIDE_BACKEND_SCRIPT ""
#endif

AnalysisBackend::AnalysisBackend(QObject *parent)
    : QObject(parent)
{
    m_script = qEnvironmentVariable("OFFSIDE_BACKEND", QStringLiteral(OFFSIDE_BACKEND_SCRIPT));
    m_python = qEnvironmentVariable("OFFSIDE_PYTHON", QStringLiteral("python3"));
    connect(&m_process, &QProcess::readyReadStandardOutput, this, &AnalysisBackend::readOutput);
    connect(&m_process, &QProcess::readyReadStandardError, this, &AnalysisBackend::readErrors);
    connect(&m_process, &QProcess::finished, this, &AnalysisBackend::onFinished);
}

AnalysisBackend::~AnalysisBackend()
{
    if (m_process.state() == QProcess::NotRunning)
        return;
    disconnect(&m_process, nullptr, this, nullptr);
    // On exit the server closes the HRNet container: give it a few seconds
    m_process.write("{\"id\":0,\"cmd\":\"quit\"}\n");
    m_process.closeWriteChannel();
    if (!m_process.waitForFinished(15000))
        m_process.kill();
}

bool AnalysisBackend::ensureStarted()
{
    if (m_process.state() != QProcess::NotRunning)
        return true;
    const QFileInfo script(m_script);
    if (!script.exists()) {
        failPending(QStringLiteral("No se encuentra el servidor de análisis (%1). Indica su ruta con OFFSIDE_BACKEND.")
                        .arg(m_script));
        return false;
    }
    m_buffer.clear();
    m_errors.clear();
    m_process.setWorkingDirectory(script.absolutePath());
    m_process.start(m_python, {QStringLiteral("-u"), script.absoluteFilePath()});
    if (!m_process.waitForStarted(10000)) {
        failPending(QStringLiteral("No se puede arrancar %1: %2").arg(m_python, m_process.errorString()));
        return false;
    }
    setStatus(QStringLiteral("Arrancando el análisis…"));
    return true;
}

int AnalysisBackend::request(const QString &command, const QVariantMap &args)
{
    const int id = m_next++;
    m_pending.insert(id);
    emit busyChanged();
    if (!ensureStarted())
        return id;
    QJsonObject message{{QStringLiteral("id"), id}, {QStringLiteral("cmd"), command},
                        {QStringLiteral("args"), QJsonObject::fromVariantMap(args)}};
    m_process.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
    return id;
}

void AnalysisBackend::readOutput()
{
    m_buffer += m_process.readAllStandardOutput();
    int end;
    while ((end = m_buffer.indexOf('\n')) >= 0) {
        const QByteArray line = m_buffer.left(end).trimmed();
        m_buffer.remove(0, end + 1);
        if (line.isEmpty())
            continue;
        QJsonParseError error;
        const QJsonObject message = QJsonDocument::fromJson(line, &error).object();
        if (error.error != QJsonParseError::NoError) {
            qWarning().noquote() << "Línea del servidor de análisis que no es JSON:" << line;
            continue;
        }
        if (message.contains(QStringLiteral("progress"))) {
            setStatus(message.value(QStringLiteral("progress")).toString());
            continue;
        }
        if (message.contains(QStringLiteral("event")))
            continue;
        const int id = message.value(QStringLiteral("id")).toInt();
        m_pending.remove(id);
        emit busyChanged();
        if (m_pending.isEmpty())
            setStatus(QString());
        emit replied(id, message.toVariantMap());
    }
}

void AnalysisBackend::readErrors()
{
    const QByteArray text = m_process.readAllStandardError();
    qInfo().noquote() << QString::fromUtf8(text).trimmed();
    m_errors = (m_errors + text).right(4000);
}

void AnalysisBackend::onFinished()
{
    QStringList lines = QString::fromUtf8(m_errors).trimmed().split(QLatin1Char('\n'));
    const QString last = lines.mid(qMax(0, lines.size() - 3)).join(QLatin1Char('\n'));
    failPending(QStringLiteral("El servidor de análisis se ha cerrado (código %1)%2")
                    .arg(m_process.exitCode())
                    .arg(last.isEmpty() ? QString() : QStringLiteral(":\n") + last));
}

void AnalysisBackend::failPending(const QString &error)
{
    const QSet<int> pending = m_pending;
    m_pending.clear();
    emit busyChanged();
    setStatus(QString());
    for (int id : pending)
        emit replied(id, {{QStringLiteral("id"), id}, {QStringLiteral("ok"), false}, {QStringLiteral("error"), error}});
}

void AnalysisBackend::setStatus(const QString &status)
{
    if (status == m_status)
        return;
    m_status = status;
    emit statusChanged();
}
