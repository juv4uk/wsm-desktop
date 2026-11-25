// SPDX-License-Identifier: LicenseRef-Volnist

#include "PreflightController.h"

#include <QCoreApplication>
#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QDir>
#include <QGuiApplication>
#include <cstdlib>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>
#include <QTimer>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("WSM Installer"));
    QCoreApplication::setApplicationVersion(QStringLiteral("0.1.0"));

    QCommandLineParser parser;
    parser.addHelpOption();
    parser.addVersionOption();
    const QCommandLineOption smokeTestOption(
        QStringList{QStringLiteral("smoke-test")},
        QStringLiteral("Load the QML interface and exit without probing hardware."));
    parser.addOption(smokeTestOption);
    parser.process(app);
    const bool smokeTest = parser.isSet(smokeTestOption);

    PreflightController controller;
    QQmlApplicationEngine engine;
#ifdef WSM_QML_IMPORT_PATH
    const QString qmlImportPaths = QStringLiteral(WSM_QML_IMPORT_PATH);
    for (const QString &path : qmlImportPaths.split(QDir::listSeparator(), Qt::SkipEmptyParts))
        engine.addImportPath(path);
#endif

    engine.rootContext()->setContextProperty(
        QStringLiteral("wsmController"), &controller);
    engine.rootContext()->setContextProperty(
        QStringLiteral("wsmSmokeTest"), smokeTest);

    const QUrl mainUrl(
        QStringLiteral("qrc:/qt/qml/WSM/Installer/Main.qml"));

    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreated,
        &app,
        [mainUrl](QObject *object, const QUrl &url) {
            if (!object && url == mainUrl)
                QCoreApplication::exit(EXIT_FAILURE);
        },
        Qt::QueuedConnection);

    engine.load(mainUrl);
    if (engine.rootObjects().isEmpty())
        return EXIT_FAILURE;

    if (smokeTest)
        QTimer::singleShot(0, &app, &QCoreApplication::quit);

    return app.exec();
}
