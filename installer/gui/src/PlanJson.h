// SPDX-License-Identifier: LicenseRef-Volnist

#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QString>

namespace WsmPlanJson {

QByteArray canonicalJson(const QJsonObject &object);
bool validateDiagnosticPlan(const QJsonObject &plan,
                            const QByteArray &reportBytes,
                            QString *error);

} // namespace WsmPlanJson
