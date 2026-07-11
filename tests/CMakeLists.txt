add_executable(test_basic test_basic.cpp)
target_include_directories(test_basic PRIVATE ${CMAKE_SOURCE_DIR}/third_party/doctest)
target_link_libraries(test_basic PRIVATE light_config)
add_test(NAME light_config_basic COMMAND test_basic)

# Edge-probe library test (runtime scenarios re-hosted from
# build/edge_probes/runtime_probe.cpp; asserts desired behavior for the
# edge-probe findings).
add_executable(test_edge_probes test_edge_probes.cpp)
target_include_directories(test_edge_probes PRIVATE ${CMAKE_SOURCE_DIR}/third_party/doctest)
target_link_libraries(test_edge_probes PRIVATE light_config)
add_test(NAME light_config_edge_probes COMMAND test_edge_probes)

# Python generator self-tests
find_program(PYTHON3_EXE NAMES python3 python)
if(PYTHON3_EXE)
    add_test(NAME gen_config_self_test
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_gen_config.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    add_test(NAME gen_config_metadata
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_metadata.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    add_test(NAME gen_config_provenance
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_provenance.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    add_test(NAME gen_config_provenance_build
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_provenance_build.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    add_test(NAME gen_config_stamp_emit
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_stamp_emit.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    # Compiles the generated C++ for the full type matrix and rejects
    # generator inputs that would emit non-compiling code (generator defects).
    # Requires a C++17 compiler on PATH; skips compile checks gracefully
    # when none is present (rejection checks still run).
    add_test(NAME gen_config_cpp_compile
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_cpp_compile.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
    add_test(NAME gen_config_edge_probes
             COMMAND ${PYTHON3_EXE} ${CMAKE_SOURCE_DIR}/scripts/test_edge_probes.py
             WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}/scripts)
endif()
