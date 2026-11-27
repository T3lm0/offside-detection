#pragma once

#include <QByteArray>
#include <QObject>
#include <QProcess>
#include <QSet>
#include <QUrl>
#include <QVariantMap>
#include <QtQml/qqmlregistration.h>

// Python analysis server (scripts/inference/offside_backend.py), started with QProcess the first
// time something is requested and kept open until the application closes (so the models load only
// once). They talk in JSON lines: each request carries a number and its response arrives through
// replied(); while working it sends progress messages (status).
//
// The script and the interpreter can be changed with the OFFSIDE_BACKEND and OFFSIDE_PYTHON variables.
class AnalysisBackend : public QObject
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString script READ script CONSTANT)

public:
    explicit AnalysisBackend(QObject *parent = nullptr);
    ~AnalysisBackend() override;

    bool busy() const { return !m_pending.isEmpty(); }
    QString status() const { return m_status; }
    QString script() const { return m_script; }

    // Returns the request number (the one its response carries in replied)
    Q_INVOKABLE int request(const QString &command, const QVariantMap &args = {});
    Q_INVOKABLE QString localPath(const QUrl &url) const { return url.toLocalFile(); }
    Q_INVOKABLE QUrl fileUrl(const QString &path) const { return QUrl::fromLocalFile(path); }

signals:
    void replied(int id, const QVariantMap &reply);
    void busyChanged();
    void statusChanged();

private:
    bool ensureStarted();
    void readOutput();
    void readErrors();
    void onFinished();
    void failPending(const QString &error);
    void setStatus(const QString &status);

    QProcess m_process;
    QString m_script;
    QString m_python;
    QByteArray m_buffer;
    QByteArray m_errors; // tail of stderr, to explain an unexpected exit
    QSet<int> m_pending;
    int m_next = 1;
    QString m_status;
};
