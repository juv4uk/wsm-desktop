// SPDX-License-Identifier: LicenseRef-Volnist

#include "PreflightController.h"

#include <QDir>
#include <algorithm>
#include <QFile>
#include <QJsonArray>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QProcess>
#include <QSaveFile>
#include <QProcessEnvironment>
#include <QStandardPaths>
#include <QTimer>
#include <QRegularExpression>
#include <QTemporaryDir>

namespace {
constexpr qsizetype kMaximumStdoutBytes = 16 * 1024 * 1024;
constexpr qsizetype kMaximumStderrBytes = 1024 * 1024;

QString jsonString(const QJsonObject &object, const QString &key,
                   const QString &fallback = QStringLiteral("unknown"))
{
    const QJsonValue value = object.value(key);
    return value.isString() && !value.toString().isEmpty()
        ? value.toString() : fallback;
}

QString firstNonEmpty(const QString &first, const QString &second,
                      const QString &fallback)
{
    if (!first.trimmed().isEmpty())
        return first;
    if (!second.trimmed().isEmpty())
        return second;
    return fallback;
}

QString categoryLabel(const QString &category)
{
    if (category == QStringLiteral("cpu")) return QStringLiteral("Процесор");
    if (category == QStringLiteral("motherboard")) return QStringLiteral("Материнська плата");
    if (category == QStringLiteral("memory")) return QStringLiteral("Пам’ять");
    if (category == QStringLiteral("storage-controller")) return QStringLiteral("Контролер сховища");
    if (category == QStringLiteral("storage-device")) return QStringLiteral("Накопичувач");
    if (category == QStringLiteral("network")) return QStringLiteral("Мережа");
    if (category == QStringLiteral("gpu")) return QStringLiteral("Графічний пристрій");
    if (category == QStringLiteral("display")) return QStringLiteral("Дисплей");
    if (category == QStringLiteral("audio")) return QStringLiteral("Аудіо");
    if (category == QStringLiteral("input")) return QStringLiteral("Пристрій введення");
    if (category == QStringLiteral("bluetooth")) return QStringLiteral("Bluetooth");
    if (category == QStringLiteral("usb-controller")) return QStringLiteral("USB-контролер");
    return category.isEmpty() ? QStringLiteral("Невідома категорія") : category;
}

QString driverLabel(const QString &status)
{
    if (status == QStringLiteral("bound")) return QStringLiteral("драйвер прив’язаний");
    if (status == QStringLiteral("module-loaded-unbound")) return QStringLiteral("модуль завантажений, не прив’язаний");
    if (status == QStringLiteral("available-only")) return QStringLiteral("лише кандидат");
    if (status == QStringLiteral("none-known")) return QStringLiteral("кандидат не знайдений");
    if (status == QStringLiteral("not-applicable")) return QStringLiteral("не застосовується");
    if (status == QStringLiteral("error")) return QStringLiteral("помилка");
    return QStringLiteral("невідомо");
}

QString firmwareLabel(const QString &status)
{
    if (status == QStringLiteral("loaded")) return QStringLiteral("завантажено");
    if (status == QStringLiteral("available-not-confirmed-loaded")) return QStringLiteral("є файл, завантаження не підтверджено");
    if (status == QStringLiteral("missing")) return QStringLiteral("відсутня");
    if (status == QStringLiteral("load-error")) return QStringLiteral("помилка завантаження");
    if (status == QStringLiteral("not-needed")) return QStringLiteral("не потрібна");
    return QStringLiteral("невідомо");
}

QString sizeLabel(quint64 bytes)
{
    constexpr double kib = 1024.0;
    constexpr double mib = kib * 1024.0;
    constexpr double gib = mib * 1024.0;
    constexpr double tib = gib * 1024.0;

    if (bytes >= static_cast<quint64>(tib))
        return QStringLiteral("%1 TiB").arg(static_cast<double>(bytes) / tib, 0, 'f', 2);
    if (bytes >= static_cast<quint64>(gib))
        return QStringLiteral("%1 GiB").arg(static_cast<double>(bytes) / gib, 0, 'f', 1);
    if (bytes >= static_cast<quint64>(mib))
        return QStringLiteral("%1 MiB").arg(static_cast<double>(bytes) / mib, 0, 'f', 0);
    return QStringLiteral("%1 bytes").arg(bytes);
}

QString jsonValueString(const QJsonValue &value)
{
    if (value.isString())
        return value.toString();
    if (value.isDouble())
        return QString::number(value.toDouble(), 'f', 0);
    if (value.isBool())
        return value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    return {};
}

bool jsonBool(const QJsonValue &value)
{
    if (value.isBool())
        return value.toBool();
    if (value.isDouble())
        return value.toInt() != 0;
    if (value.isString())
        return value.toString() == QStringLiteral("1")
            || value.toString().compare(QStringLiteral("true"), Qt::CaseInsensitive) == 0;
    return false;
}

} // namespace

PreflightController::PreflightController(QObject *parent)
    : QObject(parent)
{
}

PreflightController::~PreflightController() = default;

bool PreflightController::busy() const { return m_busy; }
bool PreflightController::reportReady() const { return m_reportReady; }
QString PreflightController::status() const { return m_status; }
QString PreflightController::error() const { return m_error; }
QVariantMap PreflightController::environment() const { return m_environment; }
QVariantList PreflightController::devices() const { return m_devices; }
QVariantList PreflightController::disks() const { return m_disks; }
QString PreflightController::diskInventoryState() const { return m_diskInventoryState; }
QString PreflightController::selectedDisk() const { return m_selectedDisk; }
bool PreflightController::planAvailable() const { return m_planAvailable; }
QString PreflightController::planStatus() const { return m_planStatus; }
QString PreflightController::planDigest() const { return m_planDigest; }
QVariantList PreflightController::planWarnings() const { return m_planWarnings; }
QVariantList PreflightController::planBlockers() const { return m_planBlockers; }

QString PreflightController::pythonExecutable() const
{
#ifdef WSM_PYTHON_EXECUTABLE
    return QStringLiteral(WSM_PYTHON_EXECUTABLE);
#else
    return QStandardPaths::findExecutable(QStringLiteral("python3"));
#endif
}

QString PreflightController::lsblkExecutable() const
{
#ifdef WSM_LSBLK_EXECUTABLE
    return QStringLiteral(WSM_LSBLK_EXECUTABLE);
#else
    return QStandardPaths::findExecutable(QStringLiteral("lsblk"));
#endif
}

void PreflightController::setBusy(bool value)
{
    if (m_busy == value)
        return;
    m_busy = value;
    emit busyChanged();
}

void PreflightController::setStatus(const QString &value)
{
    if (m_status == value)
        return;
    m_status = value;
    emit statusChanged();
}

void PreflightController::setError(const QString &value)
{
    if (m_error == value)
        return;
    m_error = value;
    emit errorChanged();
}

void PreflightController::refreshHardware()
{
    if (m_busy) {
        setError(QStringLiteral("Дочекайтеся завершення поточної операції."));
        return;
    }

    setError({});
    m_reportReady = false;
    m_planAvailable = false;
    m_planStatus = QStringLiteral("not-run");
    m_planDigest.clear();
    m_environment.clear();
    m_devices.clear();
    const bool hadDiskSelection = !m_selectedDisk.isEmpty();
    m_disks.clear();
    m_selectedDisk.clear();
    m_diskInventoryState = QStringLiteral("not-run");
    m_planWarnings.clear();
    m_planBlockers.clear();
    m_reportBytes.clear();
    m_reportPath.clear();
    m_temporaryDirectory.reset();
    emit reportReadyChanged();
    emit disksChanged();
    if (hadDiskSelection)
        emit selectedDiskChanged();
    emit planChanged();

    const QString python = pythonExecutable();
    if (python.isEmpty()) {
        setError(QStringLiteral("Не знайдено python3 у середовищі WSM."));
        setStatus(QStringLiteral("Не вдалося запустити апаратну перевірку."));
        return;
    }

    setStatus(QStringLiteral("Збираємо локальні апаратні відомості. Нічого не змінюємо."));
    startProcess(ProcessPurpose::HardwareReport,
                 python,
                 {QStringLiteral("-m"), QStringLiteral("wsm_hwcheck")});
}

void PreflightController::refreshDisks()
{
    if (m_busy) {
        setError(QStringLiteral("Дочекайтеся завершення поточної операції."));
        return;
    }

    setError({});
    const QString previousSelection = m_selectedDisk;
    m_disks.clear();
    m_selectedDisk.clear();
    m_diskInventoryState = QStringLiteral("loading");
    emit disksChanged();
    if (!previousSelection.isEmpty())
        emit selectedDiskChanged();

    const QString lsblk = lsblkExecutable();
    if (lsblk.isEmpty()) {
        m_diskInventoryState = QStringLiteral("unavailable");
        emit disksChanged();
        setError(QStringLiteral("Не знайдено lsblk. Список накопичувачів недоступний."));
        setStatus(QStringLiteral("Неможливо прочитати перелік накопичувачів."));
        return;
    }

    setStatus(QStringLiteral("Читаємо перелік дисків у режимі лише читання."));
    startProcess(ProcessPurpose::DiskInventory,
                 lsblk,
                 {QStringLiteral("--json"),
                  QStringLiteral("--bytes"),
                  QStringLiteral("--tree"),
                  QStringLiteral("--output"),
                  QStringLiteral("NAME,MODEL,SIZE,TYPE,TRAN,RO,RM,PATH")});
}

void PreflightController::selectDisk(const QString &devicePath)
{
    const bool knownDevice = std::any_of(
        m_disks.cbegin(), m_disks.cend(),
        [&devicePath](const QVariant &item) {
            return item.toMap().value(QStringLiteral("path")).toString() == devicePath;
        });

    if (!knownDevice) {
        setError(QStringLiteral("Можна вибрати лише диск із поточного read-only списку."));
        return;
    }

    setError({});
    if (m_selectedDisk == devicePath)
        return;
    m_selectedDisk = devicePath;
    emit selectedDiskChanged();
}

void PreflightController::clearDiskSelection()
{
    if (m_selectedDisk.isEmpty())
        return;
    m_selectedDisk.clear();
    emit selectedDiskChanged();
}

void PreflightController::startProcess(ProcessPurpose purpose,
                                       const QString &program,
                                       const QStringList &arguments)
{
    if (program.isEmpty()) {
        if (purpose == ProcessPurpose::DiskInventory) {
            m_diskInventoryState = QStringLiteral("unavailable");
            emit disksChanged();
        }
        setError(QStringLiteral("Не знайдено потрібну програму в PATH."));
        return;
    }

    m_processPurpose = purpose;
    m_standardOutput.clear();
    m_standardError.clear();
    m_outputOverflow = false;
    m_processTimedOut = false;

    auto *process = new QProcess(this);
    m_process = process;
    process->setProcessChannelMode(QProcess::SeparateChannels);
    auto *timeoutTimer = new QTimer(process);
    timeoutTimer->setSingleShot(true);
    const int timeoutMs = purpose == ProcessPurpose::HardwareReport
        ? 60000 : (purpose == ProcessPurpose::DraftPlan ? 30000 : 10000);
    connect(timeoutTimer, &QTimer::timeout, process, [this, process]() {
        if (process != m_process)
            return;
        m_processTimedOut = true;
        process->terminate();
        QTimer::singleShot(1500, process, [process]() {
            if (process->state() != QProcess::NotRunning)
                process->kill();
        });
    });
    if (purpose != ProcessPurpose::DiskInventory) {
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
#ifdef WSM_GUIX_PYTHONPATH
        const QString packagedPythonPath = QStringLiteral(WSM_GUIX_PYTHONPATH);
        if (!packagedPythonPath.isEmpty()) {
            const QString separator = QDir::listSeparator();
            const QString existingGuixPath = environment.value(QStringLiteral("GUIX_PYTHONPATH"));
            const QString combinedGuixPath = packagedPythonPath
                + (existingGuixPath.isEmpty() ? QString() : separator + existingGuixPath);
            const QString existingPythonPath = environment.value(QStringLiteral("PYTHONPATH"));
            environment.insert(QStringLiteral("GUIX_PYTHONPATH"), combinedGuixPath);
            environment.insert(QStringLiteral("PYTHONPATH"),
                               combinedGuixPath + (existingPythonPath.isEmpty()
                                   ? QString() : separator + existingPythonPath));
        }
#endif
        process->setProcessEnvironment(environment);
    }

    connect(process, &QProcess::readyReadStandardOutput, this,
            [this, process]() {
        if (process != m_process)
            return;
        const QByteArray chunk = process->readAllStandardOutput();
        if (m_standardOutput.size() + chunk.size() > kMaximumStdoutBytes) {
            m_outputOverflow = true;
            process->kill();
            return;
        }
        m_standardOutput += chunk;
    });

    connect(process, &QProcess::readyReadStandardError, this,
            [this, process]() {
        if (process != m_process)
            return;
        const QByteArray chunk = process->readAllStandardError();
        if (m_standardError.size() + chunk.size() > kMaximumStderrBytes) {
            m_outputOverflow = true;
            process->kill();
            return;
        }
        m_standardError += chunk;
    });

    connect(process,
            qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
            this,
            [this, process](int exitCode, QProcess::ExitStatus exitStatus) {
        handleProcessFinished(process, exitCode,
                              exitStatus == QProcess::CrashExit);
    });

    connect(process, &QProcess::errorOccurred, this,
            [this, process](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart)
            handleProcessStartFailure(process);
    });

    setBusy(true);
    process->start(program, arguments);
    timeoutTimer->start(timeoutMs);
}

void PreflightController::handleProcessStartFailure(QProcess *process)
{
    if (process != m_process)
        return;

    const QString message = process->errorString();
    if (m_processPurpose == ProcessPurpose::DiskInventory) {
        m_diskInventoryState = QStringLiteral("unavailable");
        emit disksChanged();
    }
    m_process = nullptr;
    m_processTimedOut = false;
    process->deleteLater();
    setBusy(false);
    setError(QStringLiteral("Не вдалося запустити процес: %1").arg(message));
    setStatus(QStringLiteral("Операцію перервано до виконання."));
}

void PreflightController::handleProcessFinished(QProcess *process,
                                                int exitCode,
                                                bool crashed)
{
    if (process != m_process)
        return;

    const QByteArray finalStdout = process->readAllStandardOutput();
    const QByteArray finalStderr = process->readAllStandardError();
    if (m_standardOutput.size() + finalStdout.size() > kMaximumStdoutBytes
        || m_standardError.size() + finalStderr.size() > kMaximumStderrBytes)
        m_outputOverflow = true;
    else {
        m_standardOutput += finalStdout;
        m_standardError += finalStderr;
    }

    const bool timedOut = m_processTimedOut;
    m_processTimedOut = false;
    m_process = nullptr;
    process->deleteLater();
    setBusy(false);

    if (timedOut) {
        if (m_processPurpose == ProcessPurpose::DiskInventory) {
            m_diskInventoryState = QStringLiteral("unavailable");
            emit disksChanged();
        }
        setError(QStringLiteral("Операція перевищила обмежений час виконання та була зупинена."));
        setStatus(QStringLiteral("Операцію перервано за тайм-аутом; повторіть перевірку."));
        return;
    }
    if (m_outputOverflow) {
        if (m_processPurpose == ProcessPurpose::DiskInventory) {
            m_diskInventoryState = QStringLiteral("unavailable");
            emit disksChanged();
        }
        setError(QStringLiteral("Вивід дочірнього процесу перевищив ліміт stdout 16 MiB або stderr 1 MiB."));
        setStatus(QStringLiteral("Операцію зупинено до обробки неповної відповіді."));
        return;
    }

    switch (m_processPurpose) {
    case ProcessPurpose::HardwareReport:
        handleHardwareResult(exitCode, crashed);
        break;
    case ProcessPurpose::DraftPlan:
        handlePlanResult(exitCode, crashed);
        break;
    case ProcessPurpose::DiskInventory:
        handleDiskResult(exitCode, crashed);
        break;
    }
}

void PreflightController::handleHardwareResult(int exitCode, bool crashed)
{
    if (crashed || exitCode != 0) {
        const QString detail = QString::fromUtf8(m_standardError).trimmed();
        setError(detail.isEmpty()
                     ? QStringLiteral("wsm-hwcheck завершився з кодом %1.").arg(exitCode)
                     : detail);
        setStatus(QStringLiteral("Не вдалося зібрати апаратний звіт."));
        return;
    }

    parseHardwareReport(m_standardOutput);
    if (!m_error.isEmpty())
        return;

    m_temporaryDirectory = std::make_unique<QTemporaryDir>(
        QDir::tempPath() + QStringLiteral("/wsm-installer-XXXXXX"));
    if (!m_temporaryDirectory->isValid()) {
        m_reportReady = false;
        emit reportReadyChanged();
        setError(QStringLiteral("Не вдалося створити тимчасовий каталог для звіту."));
        return;
    }

    m_reportPath = m_temporaryDirectory->filePath(QStringLiteral("hardware-report.json"));
    QSaveFile reportFile(m_reportPath);
    if (!reportFile.open(QIODevice::WriteOnly)
        || reportFile.write(m_reportBytes) != m_reportBytes.size()
        || !reportFile.commit()) {
        m_reportReady = false;
        emit reportReadyChanged();
        setError(QStringLiteral("Не вдалося зберегти тимчасову копію апаратного звіту."));
        return;
    }

    const QString python = pythonExecutable();
    if (python.isEmpty()) {
        setError(QStringLiteral("Не знайдено python3 для перевірки JSON-звіту."));
        return;
    }

    setStatus(QStringLiteral("Перевіряємо схему звіту та готуємо diagnostic-only план."));
    startProcess(ProcessPurpose::DraftPlan,
                 python,
                 {QStringLiteral("-m"),
                  QStringLiteral("wsm_install"),
                  QStringLiteral("--preflight"),
                  QStringLiteral("--report"),
                  m_reportPath,
                  QStringLiteral("--backend"),
                  QStringLiteral("guix"),
                  QStringLiteral("--dry-run")});
}

void PreflightController::parseHardwareReport(const QByteArray &bytes)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        setError(QStringLiteral("wsm-hwcheck повернув некоректний JSON: %1")
                     .arg(parseError.errorString()));
        return;
    }

    m_reportBytes = bytes;
    const QJsonObject report = document.object();
    const QJsonObject environment = report.value(QStringLiteral("environment")).toObject();
    const QJsonObject platform = environment.value(QStringLiteral("platform")).toObject();

    m_environment = {
        {QStringLiteral("architecture"), jsonString(environment, QStringLiteral("architecture"))},
        {QStringLiteral("kernel"), jsonString(environment, QStringLiteral("kernel_release"))},
        {QStringLiteral("bootMode"), jsonString(environment, QStringLiteral("boot_mode"))},
        {QStringLiteral("virtualization"), jsonString(environment, QStringLiteral("virtualization"))},
        {QStringLiteral("board"), firstNonEmpty(
             jsonString(platform, QStringLiteral("board_name"), {}),
             jsonString(platform, QStringLiteral("product_name"), {}),
             QStringLiteral("не визначено"))},
        {QStringLiteral("vendor"), jsonString(platform, QStringLiteral("system_vendor"), {})}
    };

    m_devices.clear();
    const QJsonArray deviceArray = report.value(QStringLiteral("devices")).toArray();
    for (const QJsonValue &value : deviceArray) {
        if (!value.isObject())
            continue;

        const QJsonObject device = value.toObject();
        const QJsonObject identity = device.value(QStringLiteral("identity")).toObject();
        const QJsonObject driver = device.value(QStringLiteral("driver")).toObject();
        const QJsonObject firmware = device.value(QStringLiteral("firmware")).toObject();

        const QString deviceId = jsonString(
            device, QStringLiteral("device_id"), QStringLiteral("device"));
        const QString label = firstNonEmpty(
            jsonString(identity, QStringLiteral("model"), {}),
            jsonString(identity, QStringLiteral("manufacturer"), {}),
            deviceId);

        QStringList criticality;
        for (const QJsonValue &role : device.value(QStringLiteral("criticality")).toArray()) {
            if (role.isString())
                criticality.append(role.toString());
        }

        QStringList functionalTests;
        for (const QJsonValue &testValue : device.value(QStringLiteral("functional_tests")).toArray()) {
            const QJsonObject test = testValue.toObject();
            functionalTests.append(QStringLiteral("%1: %2")
                .arg(jsonString(test, QStringLiteral("capability")),
                     jsonString(test, QStringLiteral("status"))));
        }

        QString evidenceSummary = QStringLiteral("Джерело доказу не вказано.");
        const QJsonArray evidence = device.value(QStringLiteral("evidence")).toArray();
        if (!evidence.isEmpty()) {
            const QJsonObject firstEvidence = evidence.first().toObject();
            evidenceSummary = QStringLiteral("%1 — %2")
                .arg(jsonString(firstEvidence, QStringLiteral("source")),
                     jsonString(firstEvidence, QStringLiteral("summary")));
        }

        const QString driverStatus = jsonString(driver, QStringLiteral("status"));
        const QString firmwareStatus = jsonString(firmware, QStringLiteral("runtime_status"));
        m_devices.append(QVariantMap{
            {QStringLiteral("deviceId"), deviceId},
            {QStringLiteral("category"), categoryLabel(jsonString(device, QStringLiteral("category")))},
            {QStringLiteral("label"), label},
            {QStringLiteral("bus"), jsonString(device, QStringLiteral("bus"))},
            {QStringLiteral("discovery"), jsonString(device, QStringLiteral("discovery_status"))},
            {QStringLiteral("driver"), driverLabel(driverStatus)},
            {QStringLiteral("driverModule"), jsonString(driver, QStringLiteral("bound_driver"), {})},
            {QStringLiteral("firmware"), firmwareLabel(firmwareStatus)},
            {QStringLiteral("criticality"), criticality.join(QStringLiteral(", "))},
            {QStringLiteral("tests"), functionalTests.isEmpty()
                 ? QStringLiteral("Функціональні тести не виконувалися.")
                 : functionalTests.join(QStringLiteral("; "))},
            {QStringLiteral("evidence"), evidenceSummary}
        });
    }

    m_reportReady = true;
    emit reportReadyChanged();
    setError({});
    setStatus(QStringLiteral("Апаратний звіт отримано. Інвентаризація не є тестом сумісності."));
}

void PreflightController::handlePlanResult(int exitCode, bool crashed)
{
    if (crashed) {
        setError(QStringLiteral("Процес wsm-install аварійно завершився."));
        setStatus(QStringLiteral("Не вдалося перевірити апаратний звіт."));
        return;
    }

    if (exitCode == 3) {
        m_planAvailable = false;
        m_planStatus = QStringLiteral("blocked");
        m_planDigest.clear();
        m_planWarnings.clear();
        m_planBlockers.clear();

        const QStringList lines = QString::fromUtf8(m_standardError)
            .split(QLatin1Char('\n'), Qt::SkipEmptyParts);
        for (const QString &line : lines) {
            const QString trimmed = line.trimmed();
            if (trimmed.startsWith(QStringLiteral("BLOCKED:")))
                m_planBlockers.append(trimmed.mid(8).trimmed());
            else if (trimmed.startsWith(QStringLiteral("WARNING:")))
                m_planWarnings.append(trimmed.mid(8).trimmed());
        }

        emit planChanged();
        setError({});
        setStatus(QStringLiteral("Критичні докази не пройшли перевірку. Перегляд доступний, встановлення — ні."));
        return;
    }

    if (exitCode != 0) {
        m_reportReady = false;
        m_devices.clear();
        m_environment.clear();
        emit reportReadyChanged();
        const QString detail = QString::fromUtf8(m_standardError).trimmed();
        setError(detail.isEmpty()
                     ? QStringLiteral("wsm-install завершився з кодом %1.").arg(exitCode)
                     : detail);
        setStatus(QStringLiteral("Звіт не пройшов перевірку схеми або планування."));
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(m_standardOutput, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        setError(QStringLiteral("wsm-install повернув некоректний JSON: %1")
                     .arg(parseError.errorString()));
        return;
    }

    const QJsonObject plan = document.object();
    QString validationError;
    if (!validateDiagnosticPlan(plan, &validationError)) {
        m_planAvailable = false;
        m_planStatus = QStringLiteral("invalid");
        m_planDigest.clear();
        m_planWarnings.clear();
        m_planBlockers.clear();
        m_reportReady = false;
        m_devices.clear();
        m_environment.clear();
        emit planChanged();
        emit reportReadyChanged();
        setError(validationError);
        setStatus(QStringLiteral("Відповідь backend не відповідає fail-closed diagnostic-only контракту."));
        return;
    }

    m_planAvailable = true;
    m_planStatus = QStringLiteral("diagnostic-only");
    m_planDigest = plan.value(QStringLiteral("plan_sha256")).toString();
    m_planWarnings = plan.value(QStringLiteral("warnings")).toArray().toVariantList();
    m_planBlockers = plan.value(QStringLiteral("blockers")).toArray().toVariantList();
    emit planChanged();

    setError({});
    setStatus(QStringLiteral("Попередній перегляд готовий. План diagnostic-only, запис на диск вимкнено."));
}

bool PreflightController::validateDiagnosticPlan(const QJsonObject &plan,
                                                  QString *error) const
{
    const QJsonValue version = plan.value(QStringLiteral("plan_version"));
    if (!version.isString() || version.toString() != QStringLiteral("0.1.0")) {
        *error = QStringLiteral("План відхилено: невідома або відсутня plan_version.");
        return false;
    }

    const QJsonValue mode = plan.value(QStringLiteral("plan_mode"));
    if (!mode.isString() || mode.toString() != QStringLiteral("dry-run")) {
        *error = QStringLiteral("План відхилено: plan_mode має бути dry-run.");
        return false;
    }

    const QJsonObject sourceReport = plan.value(QStringLiteral("source_report")).toObject();
    const QJsonValue sourceReportDigest = sourceReport.value(QStringLiteral("sha256"));
    const QByteArray expectedReportDigest =
        QCryptographicHash::hash(m_reportBytes, QCryptographicHash::Sha256).toHex();
    if (!sourceReportDigest.isString()
        || sourceReportDigest.toString().toLatin1() != expectedReportDigest) {
        *error = QStringLiteral("План відхилено: source_report.sha256 не відповідає точним байтам звіту.");
        return false;
    }

    const QJsonValue status = plan.value(QStringLiteral("plan_status"));
    if (!status.isString() || status.toString() != QStringLiteral("diagnostic-only")) {
        *error = QStringLiteral("План відхилено: plan_status відсутній або не diagnostic-only.");
        return false;
    }

    const QJsonObject backend = plan.value(QStringLiteral("backend")).toObject();
    if (backend.value(QStringLiteral("id")).toString() != QStringLiteral("guix-system")) {
        *error = QStringLiteral("План відхилено: backend не підтверджує guix-system.");
        return false;
    }

    const QJsonObject readiness = plan.value(QStringLiteral("plan_readiness")).toObject();
    const QJsonValue confirmable = readiness.value(QStringLiteral("confirmable"));
    if (!confirmable.isBool() || confirmable.toBool()) {
        *error = QStringLiteral("План відхилено: confirmable має бути явним boolean false.");
        return false;
    }

    const QJsonObject execution = plan.value(QStringLiteral("execution")).toObject();
    const struct {
        const char *name;
        bool expected;
    } requiredFlags[] = {
        {"dry_run", true},
        {"plan_confirmable", false},
        {"mutations_authorized", false},
        {"backend_invoked", false},
        {"disk_access_performed", false}
    };
    for (const auto &flag : requiredFlags) {
        const QJsonValue value = execution.value(QLatin1String(flag.name));
        if (!value.isBool() || value.toBool() != flag.expected) {
            *error = QStringLiteral("План відхилено: execution.%1 має бути явним boolean %2.")
                .arg(QLatin1String(flag.name),
                     flag.expected ? QStringLiteral("true") : QStringLiteral("false"));
            return false;
        }
    }

    if (!plan.value(QStringLiteral("warnings")).isArray()
        || !plan.value(QStringLiteral("blockers")).isArray()) {
        *error = QStringLiteral("План відхилено: warnings/blockers мають бути масивами.");
        return false;
    }

    const QString digest = plan.value(QStringLiteral("plan_sha256")).toString();
    static const QRegularExpression digestPattern(QStringLiteral("^[0-9a-f]{64}$"));
    if (!digestPattern.match(digest).hasMatch()) {
        *error = QStringLiteral("План відхилено: plan_sha256 відсутній або має некоректний формат.");
        return false;
    }

    QJsonObject unhashedPlan = plan;
    unhashedPlan.remove(QStringLiteral("plan_sha256"));
    const QByteArray canonicalPlan =
        QJsonDocument(unhashedPlan).toJson(QJsonDocument::Compact);
    const QByteArray expectedPlanDigest =
        QCryptographicHash::hash(canonicalPlan, QCryptographicHash::Sha256).toHex();
    if (digest.toLatin1() != expectedPlanDigest) {
        *error = QStringLiteral("План відхилено: plan_sha256 не відповідає canonical JSON.");
        return false;
    }
    return true;
}

void PreflightController::handleDiskResult(int exitCode, bool crashed)
{
    if (crashed || exitCode != 0) {
        const QString detail = QString::fromUtf8(m_standardError).trimmed();
        m_diskInventoryState = QStringLiteral("unavailable");
        emit disksChanged();
        setError(detail.isEmpty()
                     ? QStringLiteral("lsblk завершився з кодом %1.").arg(exitCode)
                     : detail);
        setStatus(QStringLiteral("Не вдалося прочитати перелік накопичувачів."));
        return;
    }
    parseDiskInventory(m_standardOutput);
}

void PreflightController::parseDiskInventory(const QByteArray &bytes)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        m_diskInventoryState = QStringLiteral("unavailable");
        emit disksChanged();
        setError(QStringLiteral("lsblk повернув некоректний JSON: %1")
                     .arg(parseError.errorString()));
        return;
    }

    m_disks.clear();
    const QJsonArray blockDevices = document.object()
        .value(QStringLiteral("blockdevices")).toArray();
    for (const QJsonValue &value : blockDevices) {
        const QJsonObject disk = value.toObject();
        if (jsonString(disk, QStringLiteral("type"), {}) != QStringLiteral("disk"))
            continue;

        const QString name = jsonString(disk, QStringLiteral("name"), QStringLiteral("disk"));
        const QString path = firstNonEmpty(
            jsonString(disk, QStringLiteral("path"), {}),
            QStringLiteral("/dev/%1").arg(name),
            QStringLiteral("невідомий шлях"));
        const QString model = jsonString(disk, QStringLiteral("model"), {});
        const QString transport = jsonString(disk, QStringLiteral("tran"), {});
        const QString sizeString = jsonValueString(disk.value(QStringLiteral("size")));
        bool sizeOk = false;
        const quint64 bytesValue = sizeString.toULongLong(&sizeOk);

        m_disks.append(QVariantMap{
            {QStringLiteral("name"), name},
            {QStringLiteral("path"), path},
            {QStringLiteral("model"), model.isEmpty() ? QStringLiteral("Модель не повідомлена") : model},
            {QStringLiteral("transport"), transport.isEmpty() ? QStringLiteral("невідомий транспорт") : transport},
            {QStringLiteral("size"), sizeOk ? sizeLabel(bytesValue) : QStringLiteral("розмір невідомий")},
            {QStringLiteral("readOnly"), jsonBool(disk.value(QStringLiteral("ro")))},
            {QStringLiteral("removable"), jsonBool(disk.value(QStringLiteral("rm")))}
        });
    }

    const QString previousSelection = m_selectedDisk;
    const bool selectionStillExists = std::any_of(
        m_disks.cbegin(), m_disks.cend(),
        [&previousSelection](const QVariant &item) {
            return item.toMap().value(QStringLiteral("path")).toString() == previousSelection;
        });
    if (!selectionStillExists)
        m_selectedDisk.clear();

    m_diskInventoryState = QStringLiteral("loaded");
    emit disksChanged();
    if (previousSelection != m_selectedDisk)
        emit selectedDiskChanged();

    setError({});
    if (m_disks.isEmpty())
        setStatus(QStringLiteral("lsblk не повернув фізичних дисків. Це не означає, що вони несправні."));
    else
        setStatus(QStringLiteral("Знайдено %1 дисків. Перелік отримано лише для читання; нічого не монтувалося.")
                      .arg(m_disks.size()));
}
