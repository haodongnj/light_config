# Hand-written consumer — the only file clang-tidy should analyze in this dir.
add_executable(example example.cpp app_config.cpp network_config.cpp)
target_include_directories(example PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(example PRIVATE light_config)

# Disable clang-tidy on auto-generated sources.
set_source_files_properties(
    app_config.cpp app_config.hpp network_config.cpp network_config.hpp
    PROPERTIES CXX_CLANG_TIDY ""
)
