// SPDX-License-Identifier: LicenseRef-Volnist

#include "InstallerWorkflowPolicy.h"

bool InstallerWorkflowPolicy::diskInventoryComplete(const QString &state)
{
    return state == QStringLiteral("loaded")
        || state == QStringLiteral("unavailable");
}

bool InstallerWorkflowPolicy::canEnterStep(int step,
                                           bool busy,
                                           bool reportReady,
                                           bool planAvailable,
                                           const QString &planStatus,
                                           const QString &diskInventoryState)
{
    if (step == 0 || step == 1)
        return true;

    if (busy || !reportReady)
        return false;

    const bool planReviewed = planAvailable
        || planStatus == QStringLiteral("blocked");
    if (!planReviewed)
        return false;

    if (step == 2)
        return true;

    if (step == 3 || step == 4)
        return diskInventoryComplete(diskInventoryState);

    return false;
}
