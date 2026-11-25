// SPDX-License-Identifier: LicenseRef-Volnist

import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root

    visible: true
    width: 1180
    height: 800
    minimumWidth: 920
    minimumHeight: 660
    title: qsTr("WSM Installer — попередня перевірка")
    color: "#f3f5f7"

    property int currentStep: 0
    property bool reviewAcknowledged: false
    property string hostname: "wsm-desktop"
    property string username: "wsm"

    function canOpenStep(step) {
        return wsmController.canEnterStep(step)
    }

    function enterStep(step) {
        if (!canOpenStep(step))
            return
        reviewAcknowledged = false
        if (step === 2 && currentStep !== 2
                && wsmController.diskInventoryState === "not-run")
            wsmController.refreshDisks()
        currentStep = step
    }
    readonly property var stepTitles: [
        qsTr("Вступ"),
        qsTr("Обладнання"),
        qsTr("Накопичувачі"),
        qsTr("Параметри"),
        qsTr("Перегляд")
    ]

    header: ToolBar {
        height: 68
        background: Rectangle { color: "#182633" }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            spacing: 18

            Label {
                text: "WSM"
                color: "#ffffff"
                font.pixelSize: 26
                font.bold: true
            }

            Rectangle {
                width: 1
                height: 30
                color: "#52616d"
            }

            ColumnLayout {
                spacing: 1
                Label {
                    text: qsTr("Майстер передінсталяційної перевірки")
                    color: "#ffffff"
                    font.pixelSize: 16
                    font.bold: true
                }
                Label {
                    text: qsTr("Лише читання · встановлення та запис на диск не реалізовані")
                    color: "#c8d3dc"
                    font.pixelSize: 12
                }
            }

            Item { Layout.fillWidth: true }

            Label {
                text: qsTr("Прототип 0.1.0")
                color: "#c8d3dc"
                font.pixelSize: 12
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 18

        Frame {
            Layout.preferredWidth: 205
            Layout.fillHeight: true
            padding: 12
            background: Rectangle {
                color: "#ffffff"
                radius: 10
                border.color: "#dce2e8"
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                Label {
                    text: qsTr("КРОКИ")
                    color: "#647383"
                    font.pixelSize: 11
                    font.bold: true
                }

                Repeater {
                    model: root.stepTitles
                    delegate: Button {
                        Layout.fillWidth: true
                        text: (index + 1) + ".  " + modelData
                        horizontalPadding: 10
                        height: 42
                        highlighted: root.currentStep === index
                        enabled: root.canOpenStep(index)
                        onClicked: root.enterStep(index)
                    }
                }

                Item { Layout.fillHeight: true }

                Label {
                    Layout.fillWidth: true
                    text: qsTr("Цей прототип не форматує, не монтує та не змінює диски.")
                    color: "#647383"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }
        }

        Frame {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 22
            background: Rectangle {
                color: "#ffffff"
                radius: 10
                border.color: "#dce2e8"
            }

            StackLayout {
                id: pages
                anchors.fill: parent
                currentIndex: root.currentStep

                // 1. Welcome
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: pages.width
                        spacing: 16

                        Label {
                            text: qsTr("Ласкаво просимо до WSM Desktop")
                            font.pixelSize: 28
                            font.bold: true
                            color: "#182633"
                            wrapMode: Text.WordWrap
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Спочатку ми зберемо локальні відомості про обладнання, перевіримо звіт і покажемо накопичувачі. Потім ви зможете переглянути параметри майбутньої системи.")
                            font.pixelSize: 16
                            color: "#354555"
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 8
                            color: "#edf4f8"
                            border.color: "#d6e3ec"
                            implicitHeight: safetyText.implicitHeight + 28
                            Label {
                                id: safetyText
                                anchors.fill: parent
                                anchors.margins: 14
                                text: qsTr("Межі прототипу: тільки читання. Програма не викликає Guix deployment, не створює розділи, не форматує, не монтує цільові диски та не встановлює завантажувач. Кнопка завершення підтверджує лише перегляд.")
                                color: "#263d4e"
                                wrapMode: Text.WordWrap
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Дані обладнання залишаються на цьому комп’ютері. Для звіту використовується тимчасовий каталог, який видаляється після закриття програми.")
                            color: "#52616d"
                            wrapMode: Text.WordWrap
                        }

                        Button {
                            text: wsmController.busy ? qsTr("Перевірка триває…") : qsTr("Почати перевірку")
                            enabled: !wsmController.busy
                            highlighted: true
                            onClicked: {
                                root.reviewAcknowledged = false
                                wsmController.refreshHardware()
                                root.currentStep = 1
                            }
                        }
                    }
                }

                // 2. Hardware evidence
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: pages.width
                        spacing: 12

                        Label {
                            text: qsTr("Апаратні докази")
                            font.pixelSize: 25
                            font.bold: true
                            color: "#182633"
                        }

                        Label {
                            Layout.fillWidth: true
                            text: wsmController.status
                            color: "#354555"
                            wrapMode: Text.WordWrap
                        }

                        Button {
                            text: qsTr("Оновити апаратний звіт")
                            enabled: !wsmController.busy
                            onClicked: {
                                root.reviewAcknowledged = false
                                wsmController.refreshHardware()
                            }
                        }

                        Frame {
                            Layout.fillWidth: true
                            background: Rectangle { color: "#f6f8fa"; radius: 8 }
                            ColumnLayout {
                                anchors.fill: parent
                                Label {
                                    text: qsTr("Середовище")
                                    font.bold: true
                                }
                                Label {
                                    text: qsTr("Архітектура: %1 · ядро: %2 · завантаження: %3")
                                        .arg(wsmController.environment.architecture || "unknown")
                                        .arg(wsmController.environment.kernel || "unknown")
                                        .arg(wsmController.environment.bootMode || "unknown")
                                    wrapMode: Text.WordWrap
                                }
                                Label {
                                    text: qsTr("Платформа: %1 · віртуалізація: %2")
                                        .arg(wsmController.environment.board || qsTr("не визначено"))
                                        .arg(wsmController.environment.virtualization || "unknown")
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Label {
                            text: wsmController.reportReady
                                ? qsTr("Пристроїв у звіті: %1").arg(wsmController.devices.length)
                                : qsTr("Звіт ще не отримано")
                            font.bold: true
                        }

                        Repeater {
                            model: wsmController.devices
                            delegate: Frame {
                                Layout.fillWidth: true
                                padding: 12
                                background: Rectangle {
                                    color: "#ffffff"
                                    radius: 8
                                    border.color: "#dce2e8"
                                }

                                ColumnLayout {
                                    anchors.fill: parent
                                    spacing: 5
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Label {
                                            Layout.fillWidth: true
                                            text: modelData.category + " · " + modelData.label
                                            font.bold: true
                                            color: "#182633"
                                            wrapMode: Text.WordWrap
                                        }
                                        Label {
                                            text: modelData.discovery
                                            color: "#52616d"
                                        }
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: qsTr("Драйвер: %1 · firmware: %2")
                                            .arg(modelData.driver).arg(modelData.firmware)
                                        color: "#354555"
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.tests
                                        color: "#52616d"
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: modelData.evidence
                                        color: "#647383"
                                        font.pixelSize: 11
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }
                        }

                        Label {
                            visible: wsmController.planAvailable
                            Layout.fillWidth: true
                            text: qsTr("Результат перевірки плану: %1 · SHA-256: %2")
                                .arg(wsmController.planStatus)
                                .arg(wsmController.planDigest)
                            color: "#354555"
                            wrapMode: Text.WrapAnywhere
                        }

                        Repeater {
                            model: wsmController.planBlockers
                            delegate: Label {
                                Layout.fillWidth: true
                                text: qsTr("Зупинка: %1").arg(modelData)
                                color: "#9b2c2c"
                                wrapMode: Text.WordWrap
                            }
                        }

                        Repeater {
                            model: wsmController.planWarnings
                            delegate: Label {
                                Layout.fillWidth: true
                                text: qsTr("Попередження: %1").arg(modelData)
                                color: "#805b16"
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }

                // 3. Read-only storage discovery
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: pages.width
                        spacing: 12

                        Label {
                            text: qsTr("Накопичувачі")
                            font.pixelSize: 25
                            font.bold: true
                            color: "#182633"
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Список читається командою lsblk у режимі лише читання. Вибір нижче існує тільки в пам’яті UI для підсумкового перегляду; він не передається до backend і не дозволяє змінювати диск.")
                            color: "#52616d"
                            wrapMode: Text.WordWrap
                        }

                        Button {
                            text: wsmController.busy ? qsTr("Читаємо…") : qsTr("Оновити список дисків")
                            enabled: !wsmController.busy
                            onClicked: {
                                root.reviewAcknowledged = false
                                wsmController.refreshDisks()
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            text: wsmController.diskInventoryState === "not-run"
                                ? qsTr("Інвентаризацію ще не запускали.")
                                : wsmController.diskInventoryState === "loading"
                                    ? qsTr("Триває read-only інвентаризація накопичувачів…")
                                    : wsmController.diskInventoryState === "unavailable"
                                        ? qsTr("Інвентаризація недоступна. Причина показана внизу; жоден диск не можна вважати перевіреним.")
                                        : wsmController.disks.length === 0
                                            ? qsTr("Інвентаризація завершилася успішно; фізичних дисків не виявлено.")
                                            : qsTr("Інвентаризацію завершено. Виявлено дисків: %1").arg(wsmController.disks.length)
                            color: wsmController.diskInventoryState === "unavailable" ? "#9b2c2c" : "#354555"
                            font.bold: true
                            wrapMode: Text.WordWrap
                        }

                        Repeater {
                            model: wsmController.disks
                            delegate: Frame {
                                Layout.fillWidth: true
                                padding: 12
                                background: Rectangle {
                                    color: wsmController.selectedDisk === modelData.path ? "#edf4f8" : "#ffffff"
                                    radius: 8
                                    border.color: wsmController.selectedDisk === modelData.path ? "#4f7188" : "#dce2e8"
                                }
                                ColumnLayout {
                                    anchors.fill: parent
                                    Label {
                                        text: modelData.path + " · " + modelData.size
                                        font.bold: true
                                        color: "#182633"
                                    }
                                    Label {
                                        text: modelData.model + " · " + modelData.transport
                                        color: "#52616d"
                                        wrapMode: Text.WordWrap
                                    }
                                    Label {
                                        text: qsTr("Апаратний RO: %1 · знімний: %2")
                                            .arg(modelData.readOnly ? qsTr("так") : qsTr("ні"))
                                            .arg(modelData.removable ? qsTr("так") : qsTr("ні"))
                                        color: "#647383"
                                    }
                                    Button {
                                        text: wsmController.selectedDisk === modelData.path
                                            ? qsTr("Обрано для перегляду")
                                            : qsTr("Вибрати лише для перегляду")
                                        onClicked: wsmController.selectDisk(modelData.path)
                                    }
                                }
                            }
                        }

                        Button {
                            text: qsTr("Очистити вибір")
                            enabled: wsmController.selectedDisk.length > 0
                            onClicked: wsmController.clearDiskSelection()
                        }
                    }
                }

                // 4. User choices
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: pages.width
                        spacing: 14

                        Label {
                            text: qsTr("Параметри майбутньої системи")
                            font.pixelSize: 25
                            font.bold: true
                            color: "#182633"
                        }

                        Label {
                            Layout.fillWidth: true
                            text: qsTr("Ці поля зберігаються тільки у стані інтерфейсу. Поточний diagnostic-only API ще не приймає їх як install intent.")
                            color: "#52616d"
                            wrapMode: Text.WordWrap
                        }

                        Label { text: qsTr("Назва комп’ютера") }
                        TextField {
                            id: hostnameField
                            Layout.fillWidth: true
                            text: root.hostname
                            onTextChanged: root.hostname = text
                            placeholderText: "wsm-desktop"
                        }

                        Label { text: qsTr("Ім’я користувача") }
                        TextField {
                            id: usernameField
                            Layout.fillWidth: true
                            text: root.username
                            onTextChanged: root.username = text
                            placeholderText: "wsm"
                        }

                        Label { text: qsTr("Мова") }
                        ComboBox {
                            id: localeBox
                            Layout.fillWidth: true
                            model: ["uk_UA.utf8", "en_US.utf8"]
                            currentIndex: 0
                        }

                        Label { text: qsTr("Часовий пояс") }
                        ComboBox {
                            id: timezoneBox
                            Layout.fillWidth: true
                            model: ["Europe/Kyiv", "UTC"]
                            currentIndex: 0
                        }

                        Label { text: qsTr("Розкладка клавіатури") }
                        ComboBox {
                            id: keyboardBox
                            Layout.fillWidth: true
                            model: ["us,ua", "ua", "us"]
                            currentIndex: 0
                        }
                    }
                }

                // 5. Review-only completion
                ScrollView {
                    clip: true
                    ColumnLayout {
                        width: pages.width
                        spacing: 14

                        Label {
                            text: qsTr("Підсумковий перегляд")
                            font.pixelSize: 25
                            font.bold: true
                            color: "#182633"
                        }

                        Frame {
                            visible: wsmController.diskInventoryState === "unavailable"
                            Layout.fillWidth: true
                            background: Rectangle {
                                color: "#fff7e6"
                                radius: 8
                                border.color: "#ead6a8"
                            }
                            Label {
                                anchors.fill: parent
                                anchors.margins: 14
                                text: qsTr("Перелік дисків недоступний. Це не доказ відсутності або несправності накопичувачів. Дозволено лише діагностичний перегляд; дискова ціль не визначена.")
                                color: "#684c16"
                                wrapMode: Text.WordWrap
                            }
                        }

                        Frame {
                            Layout.fillWidth: true
                            background: Rectangle { color: "#f6f8fa"; radius: 8 }
                            ColumnLayout {
                                anchors.fill: parent
                                Label { text: qsTr("Параметри"); font.bold: true }
                                Label { text: qsTr("Комп’ютер: %1").arg(root.hostname) }
                                Label { text: qsTr("Користувач: %1").arg(root.username) }
                                Label { text: qsTr("Мова: %1").arg(localeBox.currentText) }
                                Label { text: qsTr("Часовий пояс: %1").arg(timezoneBox.currentText) }
                                Label { text: qsTr("Клавіатура: %1").arg(keyboardBox.currentText) }
                                Label {
                                    Layout.fillWidth: true
                                    text: qsTr("Диск для перегляду: %1")
                                        .arg(wsmController.selectedDisk.length
                                            ? wsmController.selectedDisk
                                            : qsTr("не обрано"))
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        Frame {
                            Layout.fillWidth: true
                            background: Rectangle {
                                color: "#fff7e6"
                                radius: 8
                                border.color: "#ead6a8"
                            }
                            Label {
                                anchors.fill: parent
                                anchors.margins: 14
                                text: qsTr("Це не інсталяція. План має статус diagnostic-only; поточний прототип не реалізує підтвердження запису, розбиття диска або Guix system init. Жодна зміна диска не відбудеться.")
                                color: "#684c16"
                                wrapMode: Text.WordWrap
                            }
                        }

                        Label {
                            visible: wsmController.planAvailable
                            Layout.fillWidth: true
                            text: qsTr("SHA-256 діагностичного плану: %1").arg(wsmController.planDigest)
                            color: "#52616d"
                            wrapMode: Text.WrapAnywhere
                        }

                        Button {
                            text: root.reviewAcknowledged
                                ? qsTr("Перегляд позначено завершеним")
                                : qsTr("Підтвердити лише перегляд")
                            highlighted: true
                            onClicked: root.reviewAcknowledged = true
                        }

                        Label {
                            visible: root.reviewAcknowledged
                            Layout.fillWidth: true
                            text: qsTr("Перегляд підтверджено. Натисніть «Готово», щоб закрити програму. Зміни на накопичувачах не виконувалися.")
                            color: "#28613b"
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
    }

    footer: ToolBar {
        background: Rectangle { color: "#ffffff" }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 22
            anchors.rightMargin: 22

            Label {
                Layout.fillWidth: true
                text: wsmController.error.length > 0
                    ? wsmController.error
                    : wsmController.status
                color: wsmController.error.length > 0 ? "#9b2c2c" : "#52616d"
                elide: Text.ElideRight
            }

            Button {
                text: qsTr("Назад")
                enabled: root.currentStep > 0 && !wsmController.busy
                onClicked: {
                    root.currentStep -= 1
                    root.reviewAcknowledged = false
                }
            }

            Button {
                text: root.currentStep === 4 ? qsTr("Готово") : qsTr("Далі")
                highlighted: true
                enabled: !wsmController.busy
                    && (root.currentStep === 4
                        ? root.reviewAcknowledged
                        : root.canOpenStep(root.currentStep + 1))
                onClicked: {
                    if (root.currentStep === 4) {
                        Qt.quit()
                    } else {
                        root.enterStep(root.currentStep + 1)
                    }
                }
            }
        }
    }

    Component.onCompleted: {
        if (!wsmSmokeTest)
            wsmController.refreshHardware()
    }
}
