add_executable(example_json example.cpp app_config.cpp network.cpp)
target_include_directories(example_json PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(example_json PRIVATE light_config)
