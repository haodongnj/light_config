add_executable(test_basic test_basic.cpp)
target_include_directories(test_basic PRIVATE ${CMAKE_SOURCE_DIR}/third_party/doctest)
target_link_libraries(test_basic PRIVATE light_config)
add_test(NAME light_config_basic COMMAND test_basic)
