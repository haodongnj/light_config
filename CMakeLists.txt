cmake_minimum_required(VERSION 3.16)
project(light_config VERSION 0.1.0 LANGUAGES CXX)

# ---- C++17 requirement ----
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ---- Vendored yalantinglibs (third_party/yalantinglibs) ----
set(YLT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/yalantinglibs")

# ---- Header-only library target ----
add_library(light_config INTERFACE)
target_include_directories(light_config INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
# yalantinglibs include paths (header-only for struct_json, struct_yaml)
target_include_directories(light_config SYSTEM INTERFACE
    ${YLT_DIR}/include
    ${YLT_DIR}/include/ylt/standalone
    ${YLT_DIR}/include/ylt/thirdparty
)

# ---- Examples ----
add_subdirectory(examples)

# ---- Tests ----
enable_testing()
add_subdirectory(tests)
