// SPDX-License-Identifier: LicenseRef-Volnist

#pragma once

#include <QByteArray>
#include <QObject>
#include <QString>
#include <QStringList>
#include <QVariantList>
#include <QVariantMap>

#include <memory>

class QProcess;
class QJsonObject;
class QTemporaryDir;

class PreflightController final : public QObject
{
    Q_OBJECT

    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool reportReady READ reportReady NOTIFY reportReadyChanged)
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QVariantMap environment READ environment NOTIFY reportReadyChanged)
    Q_PROPERTY(QVariantList devices READ devices NOTIFY reportReadyChanged)
    Q_PROPERTY(QVariantList disks READ disks NOTIFY disksChanged)
    Q_PROPERTY(QString diskInventoryState READ diskInventoryState NOTIFY diskInventoryChanged)
    Q_PROPERTY(QString selectedDisk READ selectedDisk NOTIFY selectedDiskChanged)
    Q_PROPERTY(bool planAvailable READ planAvailable NOTIFY planChanged)
    Q_PROPERTY(QString planStatus READ planStatus NOTIFY planChanged)
    Q_PROPERTY(QString planDigest READ planDigest NOTIFY planChanged)
    Q_PROPERTY(QVariantList planWarnings READ planWarnings NOTIFY planChanged)
    Q_PROPERTY(QVariantList planBlockers READ planBlockers NOTIFY planChanged)

public:
    explicit PreflightController(QObject *parent = nullptr);
    ~PreflightController() override;

    bool busy() const;
    bool reportReady() const;
    QString status() const;
    QString error() const;
    QVariantMap environment() const;
    QVariantList devices() const;
    QVariantList disks() const;
    QString diskInventoryState() const;
    QString selectedDisk() const;
    bool planAvailable() const;
    QString planStatus() const;
    QString planDigest() const;
    QVariantList planWarnings() const;
    QVariantList planBlockers() const;

    Q_INVOKABLE void refreshHardware();
    Q_INVOKABLE void refreshDisks();
    Q_INVOKABLE void selectDisk(const QString &devicePath);
    Q_INVOKABLE void clearDiskSelection();
    Q_INVOKABLE bool canEnterStep(int step) const;

signals:
    void busyChanged();
    void reportReadyChanged();
    void statusChanged();
    void errorChanged();
    void disksChanged();
    void diskInventoryChanged();
    void selectedDiskChanged();
    void planChanged();

private:
    enum class ProcessPurpose {
        HardwareReport,
        DraftPlan,
        DiskInventory
    };

    void startProcess(ProcessPurpose purpose,
                      const QString &program,
                      const QStringList &arguments);
    void handleProcessFinished(QProcess *process,
                               int exitCode,
                               bool crashed);
    void handleProcessStartFailure(QProcess *process);
    bool validateDiagnosticPlan(const QJsonObject &plan, QString *error) const;
    void handleHardwareResult(int exitCode, bool crashed);
    void handlePlanResult(int exitCode, bool crashed);
    void handleDiskResult(int exitCode, bool crashed);
    void parseHardwareReport(const QByteArray &bytes);
    void parseDiskInventory(const QByteArray &bytes);
    void setBusy(bool value);
    void setStatus(const QString &value);
    void setError(const QString &value);
    void setDiskInventoryState(const QString &value);
    QString pythonExecutable() const;
    QString lsblkExecutable() const;

    bool m_busy = false;
    bool m_reportReady = false;
    bool m_planAvailable = false;
    bool m_outputOverflow = false;
    bool m_processTimedOut = false;
    QString m_status = QStringLiteral("Готово до локальної перевірки.");
    QString m_error;
    QString m_selectedDisk;
    QString m_diskInventoryState = QStringLiteral("not-run");
    QString m_planStatus = QStringLiteral("not-run");
    QString m_planDigest;
    QVariantMap m_environment;
    QVariantList m_devices;
    QVariantList m_disks;
    QVariantList m_planWarnings;
    QVariantList m_planBlockers;

    ProcessPurpose m_processPurpose = ProcessPurpose::HardwareReport;
    QProcess *m_process = nullptr;
    QByteArray m_standardOutput;
    QByteArray m_standardError;
    QByteArray m_reportBytes;
    std::unique_ptr<QTemporaryDir> m_temporaryDirectory;
    QString m_reportPath;
};
