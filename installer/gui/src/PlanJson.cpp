// SPDX-License-Identifier: LicenseRef-Volnist

#include "PlanJson.h"

#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QRegularExpression>

namespace WsmPlanJson {

QByteArray canonicalJson(const QJsonObject &object)
{
    // Compact JSON is UTF-8 without insignificant whitespace. The golden
    // parity test verifies exact equivalence to Python's canonical_json().
    return QJsonDocument(object).toJson(QJsonDocument::Compact);
}

bool validateDiagnosticPlan(const QJsonObject &plan,
                           const QByteArray &reportBytes,
                           QString *error)
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
        QCryptographicHash::hash(reportBytes, QCryptographicHash::Sha256).toHex();
    if (!sourceReportDigest.isString()
        || sourceReportDigest.toString().toLatin1() != expectedReportDigest) {
        *error = QStringLiteral("План відхилено: source_report.sha256 не відповідає точним байтам звіту.");
        return false;
    }

    QJsonParseError reportParseError;
    const QJsonDocument reportDocument =
        QJsonDocument::fromJson(reportBytes, &reportParseError);
    if (reportParseError.error != QJsonParseError::NoError || !reportDocument.isObject()) {
        *error = QStringLiteral("План відхилено: валідований апаратний звіт більше не є JSON object.");
        return false;
    }
    const QJsonObject validatedReport = reportDocument.object();
    const QJsonValue expectedReportId = validatedReport.value(QStringLiteral("report_id"));
    const QJsonValue expectedSchemaVersion = validatedReport.value(QStringLiteral("schema_version"));
    const QJsonValue sourceReportId = sourceReport.value(QStringLiteral("report_id"));
    const QJsonValue sourceSchemaVersion = sourceReport.value(QStringLiteral("schema_version"));
    if (!expectedReportId.isString() || expectedReportId.toString().isEmpty()
        || !sourceReportId.isString()
        || sourceReportId.toString() != expectedReportId.toString()) {
        *error = QStringLiteral("План відхилено: source_report.report_id не збігається з перевіреним звітом.");
        return false;
    }
    if (!expectedSchemaVersion.isString() || expectedSchemaVersion.toString().isEmpty()
        || !sourceSchemaVersion.isString()
        || sourceSchemaVersion.toString() != expectedSchemaVersion.toString()) {
        *error = QStringLiteral("План відхилено: source_report.schema_version не збігається з перевіреним звітом.");
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


} // namespace WsmPlanJson
