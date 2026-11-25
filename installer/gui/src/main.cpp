// SPDX-License-Identifier: LicenseRef-Volnist

#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QProcessEnvironment>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QTemporaryFile>
#include <QTimer>
#include <QUrl>
#include <QVariantMap>

#include <utility>

class WsmController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool busy READ busy NOTIFY stateChanged)
    Q_PROPERTY(QString reportStatus READ reportStatus NOTIFY stateChanged)
    Q_PROPERTY(QString environmentSummary READ environmentSummary NOTIFY stateChanged)
    Q_PROPERTY(QVariantList deviceRows READ deviceRows NOTIFY stateChanged)
    Q_PROPERTY(QVariantList reportWarnings READ reportWarnings NOTIFY stateChanged)
    Q_PROPERTY(QString targetStatus READ targetStatus NOTIFY stateChanged)
    Q_PROPERTY(QVariantList targetRows READ targetRows NOTIFY stateChanged)
    Q_PROPERTY(QString planStatus READ planStatus NOTIFY stateChanged)
    Q_PROPERTY(QString planDigest READ planDigest NOTIFY stateChanged)
    Q_PROPERTY(QVariantList planWarnings READ planWarnings NOTIFY stateChanged)
    Q_PROPERTY(QVariantList planBlockers READ planBlockers NOTIFY stateChanged)
    Q_PROPERTY(bool backendInvoked READ backendInvoked NOTIFY stateChanged)
    Q_PROPERTY(bool diskAccessPerformed READ diskAccessPerformed NOTIFY stateChanged)
    Q_PROPERTY(QString errorText READ errorText NOTIFY stateChanged)

public:
    explicit WsmController(QString reportPath, QObject *parent = nullptr)
        : QObject(parent), m_inputReportPath(std::move(reportPath))
    {
        connect(&m_process, &QProcess::finished,
                this, &WsmController::handleProcessFinished);
        connect(&m_process, &QProcess::errorOccurred,
                this, &WsmController::handleProcessError);
    }

    bool busy() const { return m_busy; }
    QString reportStatus() const { return m_reportStatus; }
    QString environmentSummary() const { return m_environmentSummary; }
    QVariantList deviceRows() const { return m_deviceRows; }
    QVariantList reportWarnings() const { return m_reportWarnings; }
    QString targetStatus() const { return m_targetStatus; }
    QVariantList targetRows() const { return m_targetRows; }
    QString planStatus() const { return m_planStatus; }
    QString planDigest() const { return m_planDigest; }
    QVariantList planWarnings() const { return m_planWarnings; }
    QVariantList planBlockers() const { return m_planBlockers; }
    bool backendInvoked() const { return m_backendInvoked; }
    bool diskAccessPerformed() const { return m_diskAccessPerformed; }
    QString errorText() const { return m_errorText; }

    Q_INVOKABLE void refreshAll()
    {
        if (m_busy || m_process.state() != QProcess::NotRunning)
            return;

        m_errorText.clear();
        m_reportStatus = QStringLiteral("Оновлення апаратного звіту…");
        m_targetStatus = QStringLiteral("Очікує read-only перевірки накопичувачів");
        m_planStatus = QStringLiteral("Очікує перевірки звіту");
        m_planDigest.clear();
        m_deviceRows.clear();
        m_reportWarnings.clear();
        m_targetRows.clear();
        m_planWarnings.clear();
        m_planBlockers.clear();
        m_backendInvoked = false;
        m_diskAccessPerformed = false;
        m_busy = true;
        emit stateChanged();

        if (!m_inputReportPath.isEmpty()) {
            QFile input(m_inputReportPath);
            if (!input.open(QIODevice::ReadOnly)) {
                finishWithError(QStringLiteral("Не вдалося прочитати звіт: ")
                                + input.errorString());
                return;
            }
            const QByteArray bytes = input.readAll();
            input.close();
            QString error;
            if (!consumeReport(bytes, &error)) {
                finishWithError(error);
                return;
            }
            startPlanValidation();
            return;
        }

        startHardwareCollection();
    }

signals:
    void stateChanged();

private:
    enum class Action {
        None,
        CollectHardware,
        BuildPlan,
        DiscoverTargets
    };

    QString pythonPath() const
    {
#ifdef WSM_PYTHONPATH
        return QStringLiteral(WSM_PYTHONPATH);
#else
        return QString();
#endif
    }

    void startProcess(Action action, const QString &program,
                      const QStringList &arguments)
    {
        m_action = action;
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        const QString bundledPythonPath = pythonPath();
        if (!bundledPythonPath.isEmpty()) {
            const QString existing = environment.value(QStringLiteral("PYTHONPATH"));
            const QString combined = existing.isEmpty()
                ? bundledPythonPath
                : bundledPythonPath + QDir::listSeparator() + existing;
            environment.insert(QStringLiteral("PYTHONPATH"), combined);
        }
        environment.insert(QStringLiteral("PYTHONUTF8"), QStringLiteral("1"));
        m_process.setProcessEnvironment(environment);
        m_process.setProgram(program);
        m_process.setArguments(arguments);
        m_process.start();
    }

    void startHardwareCollection()
    {
        m_reportStatus = QStringLiteral("Збір read-only hardware evidence…");
        emit stateChanged();
        startProcess(Action::CollectHardware, QStringLiteral("python3"),
                     {QStringLiteral("-m"), QStringLiteral("wsm_hwcheck"),
                      QStringLiteral("--compact")});
    }

    void startPlanValidation()
    {
        m_planStatus = QStringLiteral("Перевірка звіту та формування diagnostic-only плану…");
        emit stateChanged();
        startProcess(Action::BuildPlan, QStringLiteral("python3"),
                     {QStringLiteral("-m"), QStringLiteral("wsm_install"),
                      QStringLiteral("--preflight"),
                      QStringLiteral("--report"), m_reportPath,
                      QStringLiteral("--backend"), QStringLiteral("guix"),
                      QStringLiteral("--dry-run")});
    }

    void startTargetDiscovery()
    {
        m_targetStatus = QStringLiteral("Читання block-device inventory…");
        emit stateChanged();
        startProcess(Action::DiscoverTargets, QStringLiteral("lsblk"),
                     {QStringLiteral("--json"),
                      QStringLiteral("--bytes"),
                      QStringLiteral("--output"),
                      QStringLiteral("PATH,NAME,MODEL,SIZE,TYPE,TRAN,RO,RM,MOUNTPOINTS")});
    }

    bool consumeReport(const QByteArray &bytes, QString *error)
    {
        QJsonParseError parseError{};
        const QJsonDocument document = QJsonDocument::fromJson(bytes, &parseError);
        if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
            *error = QStringLiteral("Hardware report is not a valid JSON object: ")
                     + parseError.errorString();
            return false;
        }

        const QJsonObject report = document.object();
        if (report.value(QStringLiteral("schema_version")).toString()
            != QStringLiteral("1.0.0")) {
            *error = QStringLiteral("Непідтримувана або відсутня версія схеми апаратного звіту.");
            return false;
        }

        if (m_inputReportPath.isEmpty()) {
            if (m_temporaryReport)
                delete m_temporaryReport;
            m_temporaryReport = new QTemporaryFile(
                QDir::tempPath() + QStringLiteral("/wsm-hardware-XXXXXX.json"), this);
            m_temporaryReport->setAutoRemove(true);
            if (!m_temporaryReport->open()) {
                *error = QStringLiteral("Не вдалося створити тимчасовий звіт: ")
                         + m_temporaryReport->errorString();
                return false;
            }
            if (m_temporaryReport->write(bytes) != bytes.size()
                || !m_temporaryReport->flush()) {
                *error = QStringLiteral("Не вдалося записати тимчасовий апаратний звіт.");
                return false;
            }
            m_reportPath = m_temporaryReport->fileName();
        } else {
            m_reportPath = m_inputReportPath;
        }

        populateReport(report);
        const QString reportId = report.value(QStringLiteral("report_id")).toString();
        const QString collectedAt = report.value(QStringLiteral("collected_at")).toString();
        m_reportStatus = QStringLiteral("Звіт %1 · %2").arg(reportId, collectedAt);
        emit stateChanged();
        return true;
    }

    void populateReport(const QJsonObject &report)
    {
        const QJsonObject environment = report.value(QStringLiteral("environment")).toObject();
        const QJsonObject platform = environment.value(QStringLiteral("platform")).toObject();
        QString platformName = platform.value(QStringLiteral("board_name")).toString();
        if (platformName.isEmpty())
            platformName = platform.value(QStringLiteral("system_vendor")).toString();

        QStringList parts;
        if (!platformName.isEmpty())
            parts.append(platformName);
        parts.append(environment.value(QStringLiteral("architecture")).toString());
        parts.append(QStringLiteral("kernel %1").arg(
            environment.value(QStringLiteral("kernel_release")).toString()));
        parts.append(environment.value(QStringLiteral("boot_mode")).toString());
        parts.append(environment.value(QStringLiteral("virtualization")).toString());
        m_environmentSummary = parts.join(QStringLiteral(" · "));

        m_deviceRows.clear();
        for (const QJsonValue &value : report.value(QStringLiteral("devices")).toArray()) {
            const QJsonObject device = value.toObject();
            const QJsonObject identity = device.value(QStringLiteral("identity")).toObject();
            const QJsonObject driver = device.value(QStringLiteral("driver")).toObject();
            const QJsonObject firmware = device.value(QStringLiteral("firmware")).toObject();
            const QJsonArray evidence = device.value(QStringLiteral("evidence")).toArray();

            QString label = identity.value(QStringLiteral("model")).toString();
            if (label.isEmpty())
                label = identity.value(QStringLiteral("manufacturer")).toString();
            if (label.isEmpty())
                label = device.value(QStringLiteral("category")).toString();

            QString evidenceSummary = QStringLiteral("Джерело доказів не вказане");
            if (!evidence.isEmpty())
                evidenceSummary = evidence.first().toObject()
                    .value(QStringLiteral("summary")).toString();

            QVariantMap row;
            row.insert(QStringLiteral("label"), label);
            row.insert(QStringLiteral("category"),
                       device.value(QStringLiteral("category")).toString());
            row.insert(QStringLiteral("bus"), device.value(QStringLiteral("bus")).toString());
            row.insert(QStringLiteral("discovery"),
                       device.value(QStringLiteral("discovery_status")).toString());
            row.insert(QStringLiteral("driver"),
                       driver.value(QStringLiteral("status")).toString());
            row.insert(QStringLiteral("driverName"),
                       driver.value(QStringLiteral("bound_driver")).toString(
                           driver.value(QStringLiteral("module")).toString()));
            row.insert(QStringLiteral("firmware"),
                       firmware.value(QStringLiteral("runtime_status")).toString());
            row.insert(QStringLiteral("evidence"), evidenceSummary);
            m_deviceRows.append(row);
        }

        m_reportWarnings.clear();
        for (const QJsonValue &value : report.value(QStringLiteral("warnings")).toArray())
            m_reportWarnings.append(value.toString());
        for (const QJsonValue &value : report.value(QStringLiteral("limitations")).toArray())
            m_reportWarnings.append(value.toString());
    }

    void populatePlan(const QJsonObject &plan)
    {
        m_planDigest = plan.value(QStringLiteral("plan_sha256")).toString();
        m_planStatus = plan.value(QStringLiteral("plan_status")).toString();
        const QJsonObject execution = plan.value(QStringLiteral("execution")).toObject();
        m_backendInvoked = execution.value(QStringLiteral("backend_invoked")).toBool(false);
        m_diskAccessPerformed = execution.value(QStringLiteral("disk_access_performed")).toBool(false);

        m_planWarnings.clear();
        for (const QJsonValue &value : plan.value(QStringLiteral("warnings")).toArray())
            m_planWarnings.append(value.toString());

        m_planBlockers.clear();
        for (const QJsonValue &value : plan.value(QStringLiteral("blockers")).toArray())
            m_planBlockers.append(value.toString());
    }

    static QString formatBytes(qint64 bytes)
    {
        static const QStringList units{
            QStringLiteral("B"), QStringLiteral("KiB"),
            QStringLiteral("MiB"), QStringLiteral("GiB"),
            QStringLiteral("TiB")
        };
        double value = static_cast<double>(bytes);
        int unit = 0;
        while (value >= 1024.0 && unit < units.size() - 1) {
            value /= 1024.0;
            ++unit;
        }
        return QStringLiteral("%1 %2")
            .arg(value, 0, 'f', unit == 0 ? 0 : 1)
            .arg(units.at(unit));
    }

    void populateTargets(const QJsonObject &root)
    {
        m_targetRows.clear();
        for (const QJsonValue &value : root.value(QStringLiteral("blockdevices")).toArray()) {
            const QJsonObject device = value.toObject();
            if (device.value(QStringLiteral("type")).toString() != QStringLiteral("disk"))
                continue;

            const QString path = device.value(QStringLiteral("path")).toString();
            if (path.isEmpty() || !path.startsWith(QStringLiteral("/dev/")))
                continue;

            QVariantMap row;
            row.insert(QStringLiteral("path"), path);
            row.insert(QStringLiteral("name"), device.value(QStringLiteral("name")).toString());
            row.insert(QStringLiteral("model"), device.value(QStringLiteral("model")).toString());
            row.insert(QStringLiteral("size"),
                       formatBytes(device.value(QStringLiteral("size")).toVariant().toLongLong()));
            row.insert(QStringLiteral("transport"),
                       device.value(QStringLiteral("tran")).toString().isEmpty()
                           ? QStringLiteral("невідомо")
                           : device.value(QStringLiteral("tran")).toString());
            row.insert(QStringLiteral("readOnly"),
                       device.value(QStringLiteral("ro")).toVariant().toBool());
            row.insert(QStringLiteral("removable"),
                       device.value(QStringLiteral("rm")).toVariant().toBool());
            QStringList mountpoints;
            for (const QJsonValue &mount : device.value(QStringLiteral("mountpoints")).toArray()) {
                if (!mount.toString().isEmpty())
                    mountpoints.append(mount.toString());
            }
            row.insert(QStringLiteral("mountpoints"), mountpoints.join(QStringLiteral(", ")));
            m_targetRows.append(row);
        }
        m_targetStatus = QStringLiteral("Знайдено дисків: %1 · лише читання")
                             .arg(m_targetRows.size());
    }

    void handleProcessFinished(int exitCode, QProcess::ExitStatus exitStatus)
    {
        const QByteArray output = m_process.readAllStandardOutput();
        const QByteArray errors = m_process.readAllStandardError();
        const Action completed = m_action;
        m_action = Action::None;

        if (exitStatus != QProcess::NormalExit) {
            finishWithError(QStringLiteral("Дочірній процес завершився аварійно: ")
                            + QString::fromLocal8Bit(errors));
            return;
        }

        switch (completed) {
        case Action::CollectHardware: {
            if (exitCode != 0) {
                finishWithError(QStringLiteral("wsm-hwcheck завершився з кодом %1: ")
                                .arg(exitCode) + QString::fromLocal8Bit(errors));
                return;
            }
            QString error;
            if (!consumeReport(output, &error)) {
                finishWithError(error);
                return;
            }
            startPlanValidation();
            return;
        }
        case Action::BuildPlan: {
            if (exitCode == 0) {
                QJsonParseError parseError{};
                const QJsonDocument document = QJsonDocument::fromJson(output, &parseError);
                if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
                    finishWithError(QStringLiteral("wsm-install повернув некоректний JSON plan."));
                    return;
                }
                populatePlan(document.object());
                m_planStatus = QStringLiteral("Diagnostic-only · план не підтверджується");
            } else if (exitCode == 3) {
                m_planStatus = QStringLiteral("План не видано: потрібні критичні докази");
                const QStringList lines =
                    QString::fromLocal8Bit(errors).split(QLatin1Char('\n'), Qt::SkipEmptyParts);
                for (const QString &line : lines) {
                    if (line.startsWith(QStringLiteral("BLOCKED:"))
                        || line.startsWith(QStringLiteral("WARNING:")))
                        m_planBlockers.append(line);
                }
                if (m_planBlockers.isEmpty())
                    m_planBlockers.append(QStringLiteral("Критичні докази не пройшли перевірку."));
            } else {
                m_planStatus = QStringLiteral("Помилка перевірки плану");
                m_errorText = QString::fromLocal8Bit(errors);
            }
            startTargetDiscovery();
            return;
        }
        case Action::DiscoverTargets: {
            if (exitCode == 0) {
                QJsonParseError parseError{};
                const QJsonDocument document = QJsonDocument::fromJson(output, &parseError);
                if (parseError.error == QJsonParseError::NoError && document.isObject())
                    populateTargets(document.object());
                else
                    m_targetStatus = QStringLiteral("lsblk повернув невалідний JSON");
            } else {
                m_targetStatus = QStringLiteral("Список накопичувачів недоступний");
                if (!errors.isEmpty())
                    m_errorText = QString::fromLocal8Bit(errors);
            }
            finishWorkflow();
            return;
        }
        case Action::None:
            break;
        }
        finishWorkflow();
    }

    void handleProcessError(QProcess::ProcessError error)
    {
        if (error != QProcess::FailedToStart)
            return;
        m_action = Action::None;
        finishWithError(m_process.errorString());
    }

    void finishWithError(const QString &message)
    {
        m_errorText = message;
        m_busy = false;
        m_action = Action::None;
        emit stateChanged();
    }

    void finishWorkflow()
    {
        m_busy = false;
        emit stateChanged();
    }

    QString m_inputReportPath;
    QString m_reportPath;
    QTemporaryFile *m_temporaryReport = nullptr;
    QProcess m_process;
    Action m_action = Action::None;
    bool m_busy = false;
    bool m_backendInvoked = false;
    bool m_diskAccessPerformed = false;
    QString m_reportStatus = QStringLiteral("Очікує збору");
    QString m_environmentSummary = QStringLiteral("Апаратне середовище ще не перевірене");
    QVariantList m_deviceRows;
    QVariantList m_reportWarnings;
    QString m_targetStatus = QStringLiteral("Накопичувачі ще не перевірені");
    QVariantList m_targetRows;
    QString m_planStatus = QStringLiteral("План ще не сформовано");
    QString m_planDigest;
    QVariantList m_planWarnings;
    QVariantList m_planBlockers;
    QString m_errorText;
};

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationName(QStringLiteral("WSM Installer"));
    QGuiApplication::setApplicationVersion(QStringLiteral("0.1.0"));
    QGuiApplication::setOrganizationName(QStringLiteral("WSM"));

    QCommandLineParser parser;
    parser.setApplicationDescription(
        QStringLiteral("WSM Desktop read-only graphical preflight"));
    parser.addHelpOption();
    parser.addVersionOption();

    const QCommandLineOption reportOption(
        QStringList{QStringLiteral("r"), QStringLiteral("report")},
        QStringLiteral("Read an existing hardware report instead of collecting a new one."),
        QStringLiteral("path"));
    const QCommandLineOption smokeOption(
        QStringLiteral("smoke-test"),
        QStringLiteral("Load the QML interface and exit without probing hardware."));
    parser.addOption(reportOption);
    parser.addOption(smokeOption);
    parser.process(app);

    WsmController controller(parser.value(reportOption));
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("wsm"), &controller);
    engine.load(QUrl(QStringLiteral("qrc:/wsm/qml/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;

    if (parser.isSet(smokeOption))
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    else
        controller.refreshAll();

    return app.exec();
}

#include "main.moc"
