cmake_minimum_required(VERSION 3.16)
project(light_config VERSION 0.1.0 LANGUAGES CXX)

# ---- C++17 requirement ----
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ---- Static analysis (opt-in) ----
option(ENABLE_CLANG_TIDY "Run clang-tidy during compilation" OFF)
if(ENABLE_CLANG_TIDY)
    find_program(CLANG_TIDY_EXE NAMES clang-tidy REQUIRED)
    message(STATUS "clang-tidy enabled: ${CLANG_TIDY_EXE}")

    # Resolve the macOS SDK path at configure time (avoids system-header parse
    # errors when the Homebrew LLVM doesn't auto-detect the SDK).
    if(APPLE)
        execute_process(
            COMMAND xcrun --show-sdk-path
            OUTPUT_VARIABLE MACOS_SDK_PATH
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )
    endif()

    set(CMAKE_CXX_CLANG_TIDY
        "${CLANG_TIDY_EXE}"
        "--config-file=${CMAKE_CURRENT_SOURCE_DIR}/.clang-tidy"
        "--header-filter=^(include/)"
    )
    if(APPLE AND MACOS_SDK_PATH)
        list(APPEND CMAKE_CXX_CLANG_TIDY
            "--extra-arg=-isysroot${MACOS_SDK_PATH}"
        )
    endif()
endif()

# ---- clang-format targets (always available when clang-format is on PATH) ----
find_program(CLANG_FORMAT_EXE NAMES clang-format)
if(CLANG_FORMAT_EXE)
    # Hand-written sources only — skip generated app_config.* / network.*
    set(FORMAT_SOURCES
        ${CMAKE_CURRENT_SOURCE_DIR}/include/light_config/light_config.hpp
        ${CMAKE_CURRENT_SOURCE_DIR}/include/light_config/json_loader.hpp
        ${CMAKE_CURRENT_SOURCE_DIR}/include/light_config/yaml_loader.hpp
        ${CMAKE_CURRENT_SOURCE_DIR}/include/light_config/load_result.hpp
        ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_basic.cpp
        ${CMAKE_CURRENT_SOURCE_DIR}/examples/example.cpp
    )
    add_custom_target(format
        COMMAND ${CLANG_FORMAT_EXE} -i --style=file ${FORMAT_SOURCES}
        COMMENT "Formatting hand-written C++ sources with clang-format"
    )
    add_custom_target(check-format
        COMMAND ${CLANG_FORMAT_EXE} --dry-run --Werror --style=file ${FORMAT_SOURCES}
        COMMENT "Checking clang-format compliance (dry-run)"
    )
else()
    message(WARNING "clang-format not found — format / check-format targets unavailable")
endif()

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
