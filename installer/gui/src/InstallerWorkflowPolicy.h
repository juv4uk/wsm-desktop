// SPDX-License-Identifier: LicenseRef-Volnist

#pragma once

#include <QString>

class InstallerWorkflowPolicy final
{
public:
    static bool diskInventoryComplete(const QString &state);
    static bool canEnterStep(int step,
                             bool busy,
                             bool reportReady,
                             bool planAvailable,
                             const QString &planStatus,
                             const QString &diskInventoryState);
};
