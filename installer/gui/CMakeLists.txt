# SPDX-License-Identifier: LicenseRef-Volnist
cmake_minimum_required(VERSION 3.20)

project(wsm-installer VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2)

qt_add_executable(wsm-installer
    src/main.cpp
)

qt_add_resources(wsm-installer wsm_installer_qml
    PREFIX "/wsm"
    FILES qml/Main.qml
)

target_link_libraries(wsm-installer PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
    Qt6::QuickControls2
)

if(DEFINED WSM_PYTHONPATH)
    target_compile_definitions(wsm-installer PRIVATE
        WSM_PYTHONPATH="${WSM_PYTHONPATH}"
    )
endif()

install(TARGETS wsm-installer RUNTIME DESTINATION bin)
install(FILES data/wsm-installer.desktop DESTINATION share/applications)
install(FILES data/wsm-installer.svg DESTINATION share/icons/hicolor/scalable/apps)
