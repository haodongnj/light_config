cmake_minimum_required(VERSION 3.16)
project(light_config VERSION 0.1.0 LANGUAGES CXX)

# ---- Default build type ----
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING
        "Build type: Debug, Release, RelWithDebInfo, MinSizeRel" FORCE)
endif()

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
