// SPDX-License-Identifier: LicenseRef-Volnist

#include "../src/InstallerWorkflowPolicy.h"

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
