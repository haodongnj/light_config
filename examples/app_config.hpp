#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.
///
/// --- Schema provenance ---
///   schema_version : 1.0.0
///   source_csv     : sample_config.csv
///   csv_md5        : a75c3b990d9070d6b5e7a3dd8ec5bb60
///   generated_at   : 2026-07-04T10:16:12.761500+00:00
///   generator      : light_config
/// -----------------------

#include <light_config/light_config.hpp>

#include "network.hpp"

#include <optional>
#include <string>
#include <vector>

namespace app {

struct AppConfig {
    /*
     * [sample_config.csv:4]
     *   field_name  : debug
     *   group       : AppConfig
     *   type        : bool
     *   default     : false
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Enable debug logging
     *   hpp_file    : app_config.hpp
     */
    // Enable debug logging
    bool debug = false;
    /*
     * [sample_config.csv:5]
     *   field_name  : log_file
     *   group       : AppConfig
     *   type        : string
     *   default     : /var/log/app.log
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Log file path
     *   hpp_file    : app_config.hpp
     */
    // Log file path
    std::string log_file = "/var/log/app.log";
    /*
     * [sample_config.csv:6]
     *   field_name  : log_level
     *   group       : AppConfig
     *   type        : LogLevel
     *   default     : info
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Log verbosity level
     *   hpp_file    : app_config.hpp
     */
    // Log verbosity level
    LogLevel log_level = LogLevel::info;
    /*
     * [sample_config.csv:7]
     *   field_name  : allowed_origins
     *   group       : AppConfig
     *   type        : vector<string>
     *   default     : 
     *   min         : 
     *   max         : 
     *   optional    : true
     *   description : Allowed CORS origins (optional)
     *   hpp_file    : app_config.hpp
     */
    // Allowed CORS origins (optional)
    std::optional<std::vector<std::string>> allowed_origins;
    /*
     * [sample_config.csv:8]
     *   field_name  : server
     *   group       : AppConfig
     *   type        : ServerConfig
     *   default     : 
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Backend server configuration
     *   hpp_file    : app_config.hpp
     */
    ServerConfig server;
    /*
     * [sample_config.csv:9]
     *   field_name  : connection
     *   group       : AppConfig
     *   type        : ConnectionConfig
     *   default     : 
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Connection settings
     *   hpp_file    : app_config.hpp
     */
    ConnectionConfig connection;
};
YLT_REFL(AppConfig, debug, log_file, log_level, allowed_origins, server, connection);

/// Schema version declared in the CSV __metadata__ row.
constexpr std::string_view kAppConfigSchemaVersion{"1.0.0"};

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_AppConfig(const AppConfig& cfg);

}  // namespace app