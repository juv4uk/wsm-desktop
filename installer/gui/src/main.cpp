// SPDX-License-Identifier: LicenseRef-Volnist

#include "PreflightController.h"
#include "PlanJson.h"

#include <QCoreApplication>
#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QTextStream>
#include <QGuiApplication>
#include <cstdlib>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>
#include <QTimer>
#include <cstdio>

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
    const QCommandLineOption canonicalJsonOption(
        QStringList{QStringLiteral("canonical-json")},
        QStringLiteral("Write canonical compact JSON for an input object to stdout."),
        QStringLiteral("path"));
    const QCommandLineOption validatePlanOption(
        QStringList{QStringLiteral("validate-plan")},
        QStringLiteral("Validate a diagnostic-only plan against a hardware report."),
        QStringLiteral("path"));
    const QCommandLineOption reportOption(
        QStringList{QStringLiteral("report")},
        QStringLiteral("Exact hardware report bytes used by the plan."),
        QStringLiteral("path"));
    parser.addOption(canonicalJsonOption);
    parser.addOption(validatePlanOption);
    parser.addOption(reportOption);
    parser.process(app);
    const bool smokeTest = parser.isSet(smokeTestOption);

    // Test-only read-only modes use the same C++ helpers as the GUI controller.
    // They intentionally return before QML setup or any hardware probing.
    if (parser.isSet(canonicalJsonOption)) {
        QFile input(parser.value(canonicalJsonOption));
        if (!input.open(QIODevice::ReadOnly)) {
            QTextStream(stderr) << "cannot open canonical JSON input: "
                                << input.errorString() << Qt::endl;
            return 2;
        }
        QJsonParseError parseError;
        const QJsonDocument document = QJsonDocument::fromJson(input.readAll(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            QTextStream(stderr) << "canonical JSON input must be a valid JSON object: "
                                << parseError.errorString() << Qt::endl;
            return 2;
        }
        const QByteArray canonical = WsmPlanJson::canonicalJson(document.object());
        if (fwrite(canonical.constData(), 1, static_cast<size_t>(canonical.size()), stdout)
            != static_cast<size_t>(canonical.size())) {
            QTextStream(stderr) << "failed to write canonical JSON to stdout" << Qt::endl;
            return 2;
        }
        fflush(stdout);
        return 0;
    }

    if (parser.isSet(validatePlanOption) || parser.isSet(reportOption)) {
        if (!parser.isSet(validatePlanOption) || !parser.isSet(reportOption)) {
            QTextStream(stderr) << "--validate-plan and --report must be supplied together" << Qt::endl;
            return 2;
        }
        QFile planFile(parser.value(validatePlanOption));
        QFile reportFile(parser.value(reportOption));
        if (!planFile.open(QIODevice::ReadOnly) || !reportFile.open(QIODevice::ReadOnly)) {
            QTextStream(stderr) << "cannot open plan/report input file" << Qt::endl;
            return 2;
        }
        QJsonParseError parseError;
        const QJsonDocument planDocument = QJsonDocument::fromJson(planFile.readAll(), &parseError);
        if (parseError.error != QJsonParseError::NoError || !planDocument.isObject()) {
            QTextStream(stderr) << "plan input must be a valid JSON object: "
                                << parseError.errorString() << Qt::endl;
            return 2;
        }
        QString validationError;
        if (!WsmPlanJson::validateDiagnosticPlan(
                planDocument.object(), reportFile.readAll(), &validationError)) {
            QTextStream(stderr) << validationError << Qt::endl;
            return 3;
        }
        return 0;
    }

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
