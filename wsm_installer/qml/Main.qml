// SPDX-License-Identifier: LicenseRef-Volnist
import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    objectName: "wsm-installer-window"
    width: 1040
    height: 760
    minimumWidth: 760
    minimumHeight: 560
    visible: true
    title: qsTr("WSM Installer — попередній перегляд")

    property int step: 0

    pageStack.initialPage: Kirigami.Page {
        id: previewPage
        title: qsTr("WSM Desktop")
        padding: Kirigami.Units.largeSpacing

        ColumnLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Heading {
                Layout.fillWidth: true
                level: 1
                text: qsTr("Попередня перевірка WSM")
            }

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                visible: wsmController.error.length > 0
                type: Kirigami.MessageType.Error
                text: wsmController.error
            }

            Controls.Label {
                Layout.fillWidth: true
                text: wsmController.status
                wrapMode: Text.WordWrap
            }

            StackLayout {
                id: stages
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.step

                ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { level: 2; text: qsTr("Вітаємо у WSM Desktop") }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: qsTr("Цей майстер показує докази про обладнання та готує лише діагностичний план. Він не встановлює систему, не змінює диски, не завантажує firmware і не виконує APPLY.")
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: qsTr("Мінімальний live-образ зберігає окремий консольний WSM CLI/TUI шлях відновлення.")
                        wrapMode: Text.WordWrap
                    }
                    Item { Layout.fillHeight: true }
                }

                Controls.ScrollView {
                    clip: true
                    ColumnLayout {
                        width: stages.width
                        spacing: Kirigami.Units.mediumSpacing
                        Kirigami.Heading { level: 2; text: qsTr("Апаратні докази") }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: wsmController.reportId.length
                                ? qsTr("Звіт %1 · %2").arg(wsmController.reportId).arg(wsmController.collectedAt)
                                : qsTr("Звіт ще не перевірено")
                            wrapMode: Text.WordWrap
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: wsmController.summary
                            wrapMode: Text.WordWrap
                        }
                        Repeater {
                            model: wsmController.devices
                            delegate: Controls.Frame {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        font.bold: true
                                        text: modelData.category + " · " + modelData.label
                                        wrapMode: Text.WordWrap
                                    }
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        text: qsTr("Виявлення: %1 · драйвер: %2 (%3) · firmware: %4")
                                            .arg(modelData.discoveryStatus)
                                            .arg(modelData.driverStatus)
                                            .arg(modelData.boundDriver)
                                            .arg(modelData.firmwareStatus)
                                        wrapMode: Text.WordWrap
                                    }
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        text: modelData.evidence
                                        wrapMode: Text.WordWrap
                                    }
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        text: modelData.functionalTests.length
                                            ? JSON.stringify(modelData.functionalTests)
                                            : qsTr("Функціональні тести не виконувалися.")
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }
                        Controls.Button {
                            text: qsTr("Оновити апаратний звіт")
                            enabled: wsmController.state !== "loading"
                            onClicked: wsmController.refresh()
                        }
                    }
                }

                Controls.ScrollView {
                    clip: true
                    ColumnLayout {
                        width: stages.width
                        spacing: Kirigami.Units.mediumSpacing
                        Kirigami.Heading { level: 2; text: qsTr("Накопичувачі") }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("Список читається з sysfs. Жоден /dev вузол не відкривається, не монтується і не змінюється.")
                            wrapMode: Text.WordWrap
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("Стан інвентаризації: %1").arg(wsmController.diskInventoryState)
                        }
                        Repeater {
                            model: wsmController.disks
                            delegate: Controls.Frame {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    anchors.fill: parent
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        font.bold: true
                                        text: modelData.path + " · " + modelData.model
                                        wrapMode: Text.WordWrap
                                    }
                                    Controls.Label {
                                        text: qsTr("%1 байт · %2 · знімний: %3")
                                            .arg(modelData.size_bytes)
                                            .arg(modelData.vendor)
                                            .arg(modelData.removable ? qsTr("так") : qsTr("ні"))
                                    }
                                    Controls.Button {
                                        text: wsmController.selectedDisk === modelData.path
                                            ? qsTr("Обрано для перегляду")
                                            : qsTr("Вибрати лише для перегляду")
                                        onClicked: wsmController.selectDisk(modelData.path)
                                    }
                                }
                            }
                        }
                        Controls.Button {
                            text: qsTr("Очистити вибір")
                            enabled: wsmController.selectedDisk.length > 0
                            onClicked: wsmController.clearDiskSelection()
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("Вибір диска не є дозволом на зміну. Перед переглядом ідентичність обраної цілі повторно звіряється.")
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Controls.ScrollView {
                    clip: true
                    ColumnLayout {
                        width: stages.width
                        spacing: Kirigami.Units.mediumSpacing
                        Kirigami.Heading { level: 2; text: qsTr("Підсумковий перегляд") }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: wsmController.selectedDisk.length
                                ? qsTr("Ціль лише для перегляду: %1").arg(wsmController.selectedDisk)
                                : qsTr("Ціль встановлення не вибрана.")
                            wrapMode: Text.WordWrap
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("SHA-256 звіту: %1").arg(wsmController.reportSha256)
                            wrapMode: Text.WrapAnywhere
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("SHA-256 діагностичного плану: %1").arg(wsmController.planSha256)
                            wrapMode: Text.WrapAnywhere
                        }
                        Kirigami.Heading { level: 3; text: qsTr("Попередження") }
                        Repeater {
                            model: wsmController.warnings
                            delegate: Controls.Label {
                                Layout.fillWidth: true
                                text: "• " + modelData
                                wrapMode: Text.WordWrap
                            }
                        }
                        Kirigami.Heading { level: 3; text: qsTr("Невирішені критичні докази") }
                        Repeater {
                            model: wsmController.blockers
                            delegate: Controls.Label {
                                Layout.fillWidth: true
                                text: "• " + modelData
                                wrapMode: Text.WordWrap
                            }
                        }
                        Kirigami.InlineMessage {
                            Layout.fillWidth: true
                            visible: true
                            type: Kirigami.MessageType.Information
                            text: qsTr("Це diagnostic-only preview. confirmable=false, mutations_authorized=false, backend_invoked=false, disk_access_performed=false. Система не встановлена.")
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            visible: wsmController.reviewed
                            text: qsTr("Перегляд підтверджено. Жодних змін не виконано.")
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Controls.Button {
                    text: qsTr("Скасувати")
                    onClicked: Qt.quit()
                }
                Item { Layout.fillWidth: true }
                Controls.Button {
                    objectName: "wsm-installer-back"
                    text: qsTr("Назад")
                    enabled: root.step > 0
                    onClicked: root.step -= 1
                }
                Controls.Button {
                    objectName: "wsm-installer-next"
                    text: root.step === 3 ? qsTr("Готово") : qsTr("Далі")
                    highlighted: true
                    enabled: root.step < 2
                        ? wsmController.state === "ready"
                        : root.step === 2
                            ? wsmController.canReview
                            : wsmController.reviewed
                    onClicked: {
                        if (root.step === 2) {
                            if (wsmController.review())
                                root.step = 3
                        } else if (root.step === 3) {
                            Qt.quit()
                        } else {
                            root.step += 1
                        }
                    }
                }
            }
        }
    }
}
