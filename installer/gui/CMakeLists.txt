cmake_minimum_required(VERSION 3.21)

project(wsm-installer VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Qml Quick QuickControls2)

include(GNUInstallDirs)

qt_add_executable(wsm-installer
    src/main.cpp
    src/PreflightController.cpp
    src/PreflightController.h
)

set_source_files_properties(qml/Main.qml PROPERTIES QT_RESOURCE_ALIAS Main.qml)

qt_add_qml_module(wsm-installer
    URI WSM.Installer
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/InstallerFlow.js
)

target_link_libraries(wsm-installer
    PRIVATE
        Qt6::Core
        Qt6::Gui
        Qt6::Qml
        Qt6::Quick
        Qt6::QuickControls2
)

foreach(runtime_path WSM_PYTHON_EXECUTABLE WSM_QML_IMPORT_PATH WSM_GUIX_PYTHONPATH WSM_LSBLK_EXECUTABLE)
    if(DEFINED ${runtime_path} AND NOT "${${runtime_path}}" STREQUAL "")
        target_compile_definitions(wsm-installer
            PRIVATE ${runtime_path}="${${runtime_path}}"
        )
    endif()
endforeach()

install(TARGETS wsm-installer
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

install(FILES assets/wsm-installer.desktop
    DESTINATION ${CMAKE_INSTALL_DATADIR}/applications
)

install(FILES assets/wsm-installer.svg
    DESTINATION ${CMAKE_INSTALL_DATADIR}/icons/hicolor/scalable/apps
)
