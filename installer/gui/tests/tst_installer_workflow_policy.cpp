// SPDX-License-Identifier: LicenseRef-Volnist

#include "../src/InstallerWorkflowPolicy.h"

#include <QCryptographicHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QtTest/QtTest>

class InstallerWorkflowPolicyTests final : public QObject
{
    Q_OBJECT

private slots:
    void introductionAndHardwareRemainAccessible()
    {
        QVERIFY(InstallerWorkflowPolicy::canEnterStep(
            0, true, false, false, QStringLiteral("not-run"), QStringLiteral("not-run")));
        QVERIFY(InstallerWorkflowPolicy::canEnterStep(
            1, true, false, false, QStringLiteral("not-run"), QStringLiteral("not-run")));
    }

    void storageRequiresValidatedOrExplicitlyBlockedPreflight()
    {
        QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
            2, false, false, false, QStringLiteral("not-run"), QStringLiteral("not-run")));
        QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
            2, false, true, false, QStringLiteral("invalid"), QStringLiteral("not-run")));
        QVERIFY(InstallerWorkflowPolicy::canEnterStep(
            2, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("not-run")));
        QVERIFY(InstallerWorkflowPolicy::canEnterStep(
            2, false, true, false, QStringLiteral("blocked"), QStringLiteral("not-run")));
    }

    void choicesAndReviewRequireCompletedDiskInventory()
    {
        for (const int step : {3, 4}) {
            QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
                step, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("not-run")));
            QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
                step, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("loading")));
            QVERIFY(InstallerWorkflowPolicy::canEnterStep(
                step, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("loaded")));
            QVERIFY(InstallerWorkflowPolicy::canEnterStep(
                step, false, true, false, QStringLiteral("blocked"), QStringLiteral("unavailable")));
        }
    }

    void busyProcessLocksDataDependentSteps()
    {
        for (const int step : {2, 3, 4}) {
            QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
                step, true, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("loaded")));
        }
    }

    void canonicalJsonMatchesPythonSha256GoldenVector()
    {
        QJsonObject nested;
        nested.insert(QStringLiteral("z"), QStringLiteral("останнє"));
        nested.insert(QStringLiteral("a"), QStringLiteral("перше"));

        QJsonArray values;
        values.append(1);
        values.append(1.25);
        values.append(true);
        values.append(QJsonValue(QJsonValue::Null));

        QJsonObject sample;
        sample.insert(QStringLiteral("z"), values);
        sample.insert(QStringLiteral("nested"), nested);
        sample.insert(QStringLiteral("title"), QStringLiteral("WSM український звіт"));
        sample.insert(QString::fromUtf8("α"), QStringLiteral("є"));

        const QByteArray canonical = QJsonDocument(sample).toJson(QJsonDocument::Compact);
        QCOMPARE(QString::fromUtf8(canonical),
                 QString::fromUtf8(R"({"nested":{"a":"перше","z":"останнє"},"title":"WSM український звіт","z":[1,1.25,true,null],"α":"є"})"));
        QCOMPARE(QCryptographicHash::hash(canonical, QCryptographicHash::Sha256).toHex(),
                 QByteArrayLiteral("b8a199f51ae78700198d7050bbebc0d40dc1199194c051d0196f16179df2b264"));
    }

    void invalidStepsAreRejected()
    {
        QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
            -1, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("loaded")));
        QVERIFY(!InstallerWorkflowPolicy::canEnterStep(
            5, false, true, true, QStringLiteral("diagnostic-only"), QStringLiteral("loaded")));
        QVERIFY(!InstallerWorkflowPolicy::diskInventoryComplete(QStringLiteral("not-run")));
        QVERIFY(!InstallerWorkflowPolicy::diskInventoryComplete(QStringLiteral("loading")));
        QVERIFY(InstallerWorkflowPolicy::diskInventoryComplete(QStringLiteral("loaded")));
        QVERIFY(InstallerWorkflowPolicy::diskInventoryComplete(QStringLiteral("unavailable")));
    }
};

QTEST_APPLESS_MAIN(InstallerWorkflowPolicyTests)

#include "tst_installer_workflow_policy.moc"
