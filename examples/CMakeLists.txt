# Hand-written consumer — the only file clang-tidy should analyze in this dir.
add_executable(example_json example.cpp app_config.cpp network.cpp)
target_include_directories(example_json PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(example_json PRIVATE light_config)

# Disable clang-tidy on auto-generated sources.
set_source_files_properties(
    app_config.cpp app_config.hpp network.cpp network.hpp
    PROPERTIES CXX_CLANG_TIDY ""
)
