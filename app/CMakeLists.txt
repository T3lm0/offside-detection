cmake_minimum_required(VERSION 3.21)

project(OffsideViewer VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# On Ubuntu 24.04, qt6-quick3d-dev needs qt6-shadertools-dev but does not install it
find_package(Qt6ShaderTools QUIET)
if(NOT Qt6ShaderTools_FOUND)
    message(FATAL_ERROR "Qt Quick 3D necesita qt6-shadertools-dev para compilar: sudo apt install qt6-shadertools-dev")
endif()

find_package(Qt6 6.4 REQUIRED COMPONENTS Core Gui Qml Quick Quick3D QuickControls2)
qt_standard_project_setup()

qt_add_executable(offside_viewer src/main.cpp)

qt_add_qml_module(offside_viewer
    URI OffsideViewer
    VERSION 1.0
    QML_FILES
        qml/Main.qml
        qml/OrbitCameraRig.qml
        qml/PitchScene.qml
        qml/Goal.qml
        qml/SkeletonLayer.qml
        qml/OffsideOverlay.qml
        qml/PlayerLabels.qml
        qml/StatusBadge.qml
        qml/TimelineBar.qml
        qml/SidePanel.qml
        qml/DemoDirector.qml
        qml/AnalysisPage.qml
        qml/PitchMinimap.qml
    SOURCES
        src/analysisdata.h src/analysisdata.cpp
        src/scenecontroller.h src/scenecontroller.cpp
        src/skeletoninstancing.h src/skeletoninstancing.cpp
        src/pitchgeometry.h src/pitchgeometry.cpp
        src/framerecorder.h src/framerecorder.cpp
        src/analysisbackend.h src/analysisbackend.cpp
)

# The generated QML type registration includes the headers by name
target_include_directories(offside_viewer PRIVATE src)

# Python analysis server started by the Analysis tab (can be overridden with OFFSIDE_BACKEND)
get_filename_component(OFFSIDE_BACKEND_SCRIPT
    "${CMAKE_CURRENT_SOURCE_DIR}/../scripts/inference/offside_backend.py" ABSOLUTE)
target_compile_definitions(offside_viewer PRIVATE OFFSIDE_BACKEND_SCRIPT="${OFFSIDE_BACKEND_SCRIPT}")

target_link_libraries(offside_viewer PRIVATE
    Qt6::Core Qt6::Gui Qt6::Qml Qt6::Quick Qt6::Quick3D Qt6::QuickControls2
)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(offside_viewer PRIVATE -Wall -Wextra)
endif()
