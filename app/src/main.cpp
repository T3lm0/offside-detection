#include <QCommandLineParser>
#include <QElapsedTimer>
#include <QFileInfo>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickStyle>
#include <QQuickWindow>
#include <QSurfaceFormat>
#include <QTimer>
#include <QtQuick3D/qquick3d.h>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    // Needs the application object (it probes an OpenGL context) and must run before any window opens
    QSurfaceFormat::setDefaultFormat(QQuick3D::idealSurfaceFormat());
    QGuiApplication::setApplicationName(QStringLiteral("Visor de fuera de juego"));
    QQuickStyle::setStyle(QStringLiteral("Material"));

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Visor 3D de jugadas analizadas (formato offside-analysis)."));
    parser.addHelpOption();
    parser.addPositionalArgument(QStringLiteral("archivo"), QStringLiteral("Análisis en JSON."), QStringLiteral("[archivo]"));
    const QCommandLineOption frameOption(QStringLiteral("frame"), QStringLiteral("Fotograma inicial."), QStringLiteral("n"));
    const QCommandLineOption cameraOption(QStringLiteral("camera"),
                                          QStringLiteral("Vista inicial: cenital, transmision, linea, porteria, atacante."),
                                          QStringLiteral("vista"));
    const QCommandLineOption focusOption(QStringLiteral("focus"),
                                         QStringLiteral("Primer plano de la entidad con este identificador."),
                                         QStringLiteral("id"));
    const QCommandLineOption playOption(QStringLiteral("play"), QStringLiteral("Empieza a reproducir al abrir."));
    const QCommandLineOption demoOption(QStringLiteral("demo"),
                                        QStringLiteral("Graba el vídeo de demostración guionizado en este .mp4 y sale."),
                                        QStringLiteral("mp4"));
    const QCommandLineOption demoSizeOption(QStringLiteral("demo-size"),
                                            QStringLiteral("Resolución del vídeo: 1920x1080 (horizontal) o 1080x1920 (vertical)."),
                                            QStringLiteral("AnchoxAlto"), QStringLiteral("1920x1080"));
    const QCommandLineOption screenshotOption(QStringLiteral("screenshot"),
                                              QStringLiteral("Guarda una captura de la ventana y sale."),
                                              QStringLiteral("png"));
    const QCommandLineOption sizeOption(QStringLiteral("size"), QStringLiteral("Tamaño de la ventana, p. ej. 1600x900."),
                                        QStringLiteral("AnchoxAlto"));
    // Analysis tab: the same steps as with the buttons
    const QCommandLineOption inputOption(QStringLiteral("input"),
                                         QStringLiteral("Vídeo, imagen o carpeta de fotogramas que abrir en la pestaña Análisis "
                                                        "(se puede repetir para varias imágenes). --frame es entonces el fotograma del pase."),
                                         QStringLiteral("ruta"));
    const QCommandLineOption calibrateOption(QStringLiteral("calibrate"), QStringLiteral("Calibra y detecta el fotograma al abrirlo."));
    const QCommandLineOption goalOption(QStringLiteral("goal"), QStringLiteral("Portería atacada: left o right."),
                                        QStringLiteral("lado"));
    const QCommandLineOption attackerOption(QStringLiteral("attacker"), QStringLiteral("Número del atacante en el fotograma."),
                                            QStringLiteral("n"));
    const QCommandLineOption defenderOption(QStringLiteral("defender"),
                                            QStringLiteral("Número del penúltimo defensor (si falta, se propone)."),
                                            QStringLiteral("n"));
    parser.addOptions({frameOption, cameraOption, focusOption, playOption, screenshotOption, sizeOption, demoOption,
                       demoSizeOption, inputOption, calibrateOption, goalOption, attackerOption, defenderOption});
    parser.process(app);

    QVariantMap initial;
    if (!parser.positionalArguments().isEmpty())
        initial.insert(QStringLiteral("initialSource"),
                       QUrl::fromLocalFile(QFileInfo(parser.positionalArguments().first()).absoluteFilePath()));
    initial.insert(QStringLiteral("initialFrame"), parser.isSet(frameOption) ? parser.value(frameOption).toInt() : -1);
    initial.insert(QStringLiteral("initialCamera"), parser.value(cameraOption));
    initial.insert(QStringLiteral("initialFocus"), parser.isSet(focusOption) ? parser.value(focusOption).toInt() : -1);
    initial.insert(QStringLiteral("instantCamera"), parser.isSet(screenshotOption));
    initial.insert(QStringLiteral("autoPlay"), parser.isSet(playOption));
    if (parser.isSet(demoOption)) {
        const QStringList demoSize = parser.value(demoSizeOption).split(QLatin1Char('x'));
        initial.insert(QStringLiteral("demoOutput"), QFileInfo(parser.value(demoOption)).absoluteFilePath());
        if (demoSize.size() == 2) {
            initial.insert(QStringLiteral("demoWidth"), demoSize[0].toInt());
            initial.insert(QStringLiteral("demoHeight"), demoSize[1].toInt());
        }
    }
    if (parser.isSet(inputOption)) {
        QStringList inputs;
        for (const QString &path : parser.values(inputOption))
            inputs << QFileInfo(path).absoluteFilePath();
        const bool steps = parser.isSet(goalOption) || parser.isSet(attackerOption);
        initial.insert(QStringLiteral("initialInput"), inputs);
        initial.insert(QStringLiteral("initialAnalysis"),
                       QVariantMap{{QStringLiteral("frame"), parser.isSet(frameOption) ? parser.value(frameOption).toInt() : -1},
                                   {QStringLiteral("prepare"), parser.isSet(calibrateOption) || steps},
                                   {QStringLiteral("goal"), parser.value(goalOption)},
                                   {QStringLiteral("attacker"), parser.isSet(attackerOption) ? parser.value(attackerOption).toInt() : -1},
                                   {QStringLiteral("defender"), parser.isSet(defenderOption) ? parser.value(defenderOption).toInt() : -1}});
        initial.insert(QStringLiteral("initialFrame"), -1);
    }
    const QStringList size = parser.value(sizeOption).split(QLatin1Char('x'));
    if (size.size() == 2) {
        initial.insert(QStringLiteral("width"), size[0].toInt());
        initial.insert(QStringLiteral("height"), size[1].toInt());
    }

    QQmlApplicationEngine engine;
    engine.addImportPath(QStringLiteral("qrc:/"));
    engine.setInitialProperties(initial);
    engine.load(QUrl(QStringLiteral("qrc:/OffsideViewer/qml/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;

    // Capture mode: wait until the scene has been drawn (and, with --input, until the analysis steps
    // finish), save the image and exit
    if (parser.isSet(screenshotOption)) {
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
        const QString path = parser.value(screenshotOption);
        auto *poll = new QTimer(&app);
        QElapsedTimer *clock = new QElapsedTimer;
        clock->start();
        QObject::connect(poll, &QTimer::timeout, &app, [window, path, poll, clock]() {
            if (clock->elapsed() < 3500 || (!window->property("captureReady").toBool() && clock->elapsed() < 180000))
                return;
            poll->stop();
            delete clock;
            // A moment for the last change to be drawn
            QTimer::singleShot(800, window, [window, path]() {
                const bool ok = window->grabWindow().save(path);
                QCoreApplication::exit(ok ? 0 : 2);
            });
        });
        poll->start(200);
    }
    return app.exec();
}
