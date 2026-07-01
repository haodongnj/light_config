#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.
///
/// --- Schema provenance ---
///   schema_version : unknown
///   source_csv     : sample_config.csv
///   csv_md5        : 5c09bbe5e438d6913afdcc13ca4bcef4
///   generated_at   : 2026-07-01T15:11:15.266212+00:00
///   generator      : light_config
/// -----------------------

#include <light_config/light_config.hpp>
#include <cstdint>
#include <string>
#include <vector>
#include <optional>

namespace app {

struct ServerConfig {
    /*
     * [sample_config.csv:8]
     *   field_name  : host
     *   group       : ServerConfig
     *   type        : string
     *   default     : 0.0.0.0
     *   min         : 
     *   max         : 
     *   description : IP address to bind
     *   hpp_file    : network.hpp
     */
    // IP address to bind
    std::string host = "0.0.0.0";
    /*
     * [sample_config.csv:9]
     *   field_name  : port
     *   group       : ServerConfig
     *   type        : int
     *   default     : 8080
     *   min         : 1024
     *   max         : 65535
     *   description : Listening port
     *   hpp_file    : network.hpp
     */
    // Listening port
    int32_t port = 8080;
    /*
     * [sample_config.csv:10]
     *   field_name  : backlog
     *   group       : ServerConfig
     *   type        : int
     *   default     : 128
     *   min         : 1
     *   max         : 4096
     *   description : TCP listen backlog
     *   hpp_file    : network.hpp
     */
    // TCP listen backlog
    int32_t backlog = 128;
};
YLT_REFL(ServerConfig, host, port, backlog);

struct ConnectionConfig {
    /*
     * [sample_config.csv:11]
     *   field_name  : max_connections
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 1000
     *   min         : 1
     *   max         : 100000
     *   description : Max concurrent connections
     *   hpp_file    : network.hpp
     */
    // Max concurrent connections
    int32_t max_connections = 1000;
    /*
     * [sample_config.csv:12]
     *   field_name  : timeout_sec
     *   group       : ConnectionConfig
     *   type        : double
     *   default     : 30.0
     *   min         : 0.5
     *   max         : 86400
     *   description : Connection timeout in seconds
     *   hpp_file    : network.hpp
     */
    // Connection timeout in seconds
    double timeout_sec = 30.0;
    /*
     * [sample_config.csv:13]
     *   field_name  : cert_file
     *   group       : ConnectionConfig
     *   type        : string
     *   default     : 
     *   min         : 
     *   max         : 
     *   description : TLS certificate file path (optional)
     *   hpp_file    : network.hpp
     */
    // TLS certificate file path (optional)
    std::optional<std::string> cert_file;
    /*
     * [sample_config.csv:14]
     *   field_name  : retry_times
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 3
     *   min         : 0
     *   max         : 10
     *   description : Connection retry count
     *   hpp_file    : network.hpp
     */
    // Connection retry count
    int32_t retry_times = 3;
    /*
     * [sample_config.csv:15]
     *   field_name  : allowed_ciphers
     *   group       : ConnectionConfig
     *   type        : vector<string>
     *   default     : 
     *   min         : 
     *   max         : 
     *   description : Allowed TLS cipher names (optional)
     *   hpp_file    : network.hpp
     */
    // Allowed TLS cipher names (optional)
    std::optional<std::vector<std::string>> allowed_ciphers;
};
YLT_REFL(ConnectionConfig, max_connections, timeout_sec, cert_file, retry_times, allowed_ciphers);

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ServerConfig(const ServerConfig& cfg);

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ConnectionConfig(const ConnectionConfig& cfg);

} // namespace app