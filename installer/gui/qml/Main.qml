// SPDX-License-Identifier: LicenseRef-Volnist
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    visible: true
    width: 1120
    height: 760
    minimumWidth: 900
    minimumHeight: 640
    title: "WSM Installer"
    color: "#f3f5f8"

    property int step: 0
    property string selectedTarget: ""
    property string draftHostname: "wsm-desktop"
    property string draftLocale: "uk_UA.utf8"
    property string draftTimezone: "Europe/Kyiv"
    property string draftKeyboard: "us,ua"
    property string draftUsername: "wsm"

    function nextStep() {
        if (step < 4)
            step += 1
    }

    function previousStep() {
        if (step > 0)
            step -= 1
    }

    header: ToolBar {
        contentHeight: 68
        background: Rectangle { color: "#17243a" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 28
            anchors.rightMargin: 28
            spacing: 18
            Rectangle {
                Layout.preferredWidth: 38
                Layout.preferredHeight: 38
                radius: 10
                color: "#5c8de8"
                Text {
                    anchors.centerIn: parent
                    text: "W"
                    color: "white"
                    font.pixelSize: 23
                    font.bold: true
                }
            }
            ColumnLayout {
                spacing: 1
                Text {
                    text: "WSM Desktop"
                    color: "white"
                    font.pixelSize: 18
                    font.bold: true
                }
                Text {
                    text: "Власний графічний інсталятор · попередній перегляд"
                    color: "#c7d2e3"
                    font.pixelSize: 11
                }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: ["Вітаємо", "Обладнання", "Накопичувачі", "Параметри", "Підсумок"][window.step]
                color: "#e5ecf7"
                font.pixelSize: 14
            }
            Button {
                text: "Оновити"
                enabled: !wsm.busy
                onClicked: wsm.refreshAll()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 28
        spacing: 18

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: ["Старт", "Обладнання", "Диски", "Параметри", "Перевірка"]
                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 5
                    radius: 3
                    color: index <= window.step ? "#4779d0" : "#d9e0eb"
                }
            }
        }

        Rectangle {
            visible: wsm.errorText.length > 0
            Layout.fillWidth: true
            implicitHeight: visible ? errorText.implicitHeight + 20 : 0
            radius: 8
            color: "#fff0f0"
            border.color: "#e3b2b2"
            Text {
                id: errorText
                anchors.fill: parent
                anchors.margins: 10
                text: wsm.errorText
                color: "#812f2f"
                wrapMode: Text.WordWrap
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: window.step

            Item {
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 40, 760)
                    spacing: 20
                    Text {
                        Layout.fillWidth: true
                        text: "Вітаємо у WSM Desktop"
                        font.pixelSize: 34
                        font.bold: true
                        color: "#17243a"
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Майстер перевіряє обладнання, показує наявні докази сумісності та формує лише діагностичний план GNU Guix."
                        font.pixelSize: 18
                        color: "#45546b"
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        radius: 14
                        color: "#fff4df"
                        border.color: "#edcf91"
                        implicitHeight: notice.implicitHeight + 28
                        Text {
                            id: notice
                            anchors.fill: parent
                            anchors.margins: 14
                            text: "ВАЖЛИВО: цей прототип не розмічає диски, не форматує файлові системи, не монтує розділи, не встановлює bootloader і не запускає інсталяцію. Жоден диск не змінюється."
                            color: "#6b4a12"
                            wrapMode: Text.WordWrap
                            font.pixelSize: 15
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Звіт залишається локальним. Мережеве передавання hardware probe не виконується."
                        color: "#5b687b"
                        font.pixelSize: 14
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 14
                    Text {
                        text: "Апаратні докази"
                        font.pixelSize: 27
                        font.bold: true
                        color: "#17243a"
                    }
                    Text {
                        Layout.fillWidth: true
                        text: wsm.environmentSummary
                        color: "#526176"
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: wsm.reportStatus
                            color: "#43536a"
                            font.pixelSize: 13
                        }
                        BusyIndicator {
                            running: wsm.busy
                            visible: wsm.busy
                            Layout.preferredWidth: 30
                            Layout.preferredHeight: 30
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 12
                        color: "white"
                        border.color: "#dce3ed"
                        ListView {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            clip: true
                            model: wsm.deviceRows
                            delegate: Rectangle {
                                required property var modelData
                                width: ListView.view.width
                                height: evidenceText.implicitHeight + 66
                                radius: 9
                                color: "#f7f9fc"
                                border.color: "#e4eaf2"
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 5
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text {
                                            Layout.fillWidth: true
                                            text: modelData.label + " · " + modelData.category
                                            font.bold: true
                                            font.pixelSize: 15
                                            color: "#1f3049"
                                        }
                                        Text {
                                            text: modelData.discovery
                                            color: "#43536a"
                                            font.pixelSize: 12
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: "Драйвер: " + modelData.driver + " (" + (modelData.driverName || "невідомо") + ") · Firmware: " + modelData.firmware
                                        color: "#526176"
                                        font.pixelSize: 12
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        id: evidenceText
                                        Layout.fillWidth: true
                                        text: modelData.evidence
                                        color: "#68768a"
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                            Text {
                                anchors.centerIn: parent
                                visible: wsm.deviceRows.length === 0
                                text: wsm.busy ? "Збираємо локальний звіт…" : "Немає записів про пристрої"
                                color: "#66758a"
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: wsm.reportWarnings
                            delegate: Text {
                                required property string modelData
                                Layout.fillWidth: true
                                text: "• " + modelData
                                color: "#775b23"
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 14
                    Text {
                        text: "Накопичувачі"
                        font.pixelSize: 27
                        font.bold: true
                        color: "#17243a"
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Нижче показано block devices, які бачить live-середовище. Вибір рядка є лише локальною позначкою інтерфейсу й не потрапляє до install plan."
                        color: "#526176"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 14
                    }
                    Text {
                        text: wsm.targetStatus
                        color: "#43536a"
                        font.pixelSize: 13
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 12
                        color: "white"
                        border.color: "#dce3ed"
                        ListView {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8
                            clip: true
                            model: wsm.targetRows
                            delegate: Rectangle {
                                required property var modelData
                                width: ListView.view.width
                                height: 82
                                radius: 9
                                color: window.selectedTarget === modelData.path ? "#e8f0ff" : "#f7f9fc"
                                border.color: window.selectedTarget === modelData.path ? "#4779d0" : "#e4eaf2"
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    Text {
                                        Layout.preferredWidth: 115
                                        text: modelData.path
                                        color: "#1f3049"
                                        font.bold: true
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 3
                                        Text {
                                            text: modelData.model || modelData.name
                                            color: "#1f3049"
                                            font.pixelSize: 14
                                        }
                                        Text {
                                            text: modelData.size + " · " + modelData.transport + " · " + (modelData.readOnly ? "read-only" : "не read-only") + (modelData.removable ? " · removable" : "")
                                            color: "#617086"
                                            font.pixelSize: 12
                                        }
                                        Text {
                                            text: modelData.mountpoints.length ? "Монтування: " + modelData.mountpoints : "Не показано активних mount points"
                                            color: "#617086"
                                            font.pixelSize: 11
                                        }
                                    }
                                    Button {
                                        text: window.selectedTarget === modelData.path ? "Позначено" : "Лише вибрати для огляду"
                                        onClicked: window.selectedTarget = modelData.path
                                    }
                                }
                            }
                            Text {
                                anchors.centerIn: parent
                                visible: wsm.targetRows.length === 0
                                text: "Накопичувачі не виявлені або lsblk недоступний"
                                color: "#66758a"
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Це не підтвердження цільового диска. Реальна інсталяція потребуватиме окремого повторного preflight та майбутнього APPLY safety gate."
                        color: "#8a5b20"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 12
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 40, 760)
                    spacing: 14
                    Text {
                        text: "Параметри системи"
                        font.pixelSize: 27
                        font.bold: true
                        color: "#17243a"
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Це чернетка значень. Поточний backend CLI ще не приймає ці параметри, тому вони не передаються Guix і не зберігаються."
                        color: "#8a5b20"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 13
                    }
                    Label { text: "Назва системи" }
                    TextField {
                        Layout.fillWidth: true
                        text: window.draftHostname
                        onTextChanged: window.draftHostname = text
                    }
                    Label { text: "Ім'я користувача" }
                    TextField {
                        Layout.fillWidth: true
                        text: window.draftUsername
                        onTextChanged: window.draftUsername = text
                    }
                    Label { text: "Локаль" }
                    TextField {
                        Layout.fillWidth: true
                        text: window.draftLocale
                        onTextChanged: window.draftLocale = text
                    }
                    Label { text: "Часовий пояс" }
                    TextField {
                        Layout.fillWidth: true
                        text: window.draftTimezone
                        onTextChanged: window.draftTimezone = text
                    }
                    Label { text: "Розкладки клавіатури" }
                    TextField {
                        Layout.fillWidth: true
                        text: window.draftKeyboard
                        onTextChanged: window.draftKeyboard = text
                    }
                    Label {
                        text: "Позначений диск для огляду: " + (window.selectedTarget || "не вибрано")
                        color: "#526176"
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 14
                    Text {
                        text: "Підсумок попереднього перегляду"
                        font.pixelSize: 27
                        font.bold: true
                        color: "#17243a"
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        radius: 12
                        color: "white"
                        border.color: "#dce3ed"
                        implicitHeight: reviewContent.implicitHeight + 28
                        ColumnLayout {
                            id: reviewContent
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8
                            Text {
                                text: "Статус: " + wsm.planStatus
                                color: "#1f3049"
                                font.bold: true
                                font.pixelSize: 16
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "SHA-256 плану: " + (wsm.planDigest || "не сформовано")
                                color: "#526176"
                                wrapMode: Text.WrapAnywhere
                                font.pixelSize: 12
                            }
                            Text { text: "Backend викликано: " + (wsm.backendInvoked ? "так" : "ні") }
                            Text { text: "Доступ до дисків виконано: " + (wsm.diskAccessPerformed ? "так" : "ні") }
                            Text { text: "Позначений target (лише UI): " + (window.selectedTarget || "немає") }
                            Text {
                                text: "Чернетка: " + window.draftHostname + " · " + window.draftUsername + " · " + window.draftLocale + " · " + window.draftTimezone + " · " + window.draftKeyboard
                                color: "#526176"
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                            }
                        }
                    }
                    Text { text: "Попередження"; font.pixelSize: 16; font.bold: true; color: "#17243a" }
                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 110
                        model: wsm.planWarnings
                        delegate: Text {
                            required property string modelData
                            width: ListView.view.width
                            text: "• " + modelData
                            color: "#76541d"
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                        }
                    }
                    Text { text: "Критичні причини"; font.pixelSize: 16; font.bold: true; color: "#17243a" }
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: wsm.planBlockers
                        delegate: Text {
                            required property string modelData
                            width: ListView.view.width
                            text: "• " + modelData
                            color: "#8b3434"
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Прототип завершує лише перегляд. Кнопки встановлення немає: реальна операція потребуватиме окремого підтвердженого плану та QEMU APPLY-перевірки."
                        color: "#8a5b20"
                        wrapMode: Text.WordWrap
                        font.pixelSize: 13
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#dce3ed"
        }

        RowLayout {
            Layout.fillWidth: true
            Button {
                text: "Назад"
                enabled: window.step > 0 && !wsm.busy
                onClicked: window.previousStep()
            }
            Item { Layout.fillWidth: true }
            Text {
                text: (window.step + 1) + " / 5"
                color: "#65748a"
            }
            Button {
                text: window.step === 4 ? "Завершити перегляд" : "Далі"
                enabled: !wsm.busy
                highlighted: true
                onClicked: {
                    if (window.step === 4)
                        Qt.quit()
                    else
                        window.nextStep()
                }
            }
        }
    }
}
