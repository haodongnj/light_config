#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.
///
/// --- Schema provenance ---
///   schema_version : 1.0.0
///   source_csv     : sample_config.csv
///   csv_md5        : 9bd084c1c88cb838bf8cd819e637de54
///   generated_at   : 2026-07-05T02:25:23.039203+00:00
///   generator      : light_config
/// -----------------------

#include <light_config/light_config.hpp>
#include <string>
#include <vector>
#include <cstdint>
#include <optional>
#include <array>
/*
 * [network_config.hpp:__enum__ row]
 *   enum_name   : LogLevel
 *   enumerators : 4
 *   hpp_file    : network_config.hpp
 */
enum class LogLevel { debug = 0, info = 1, warn = 2, error = 3 };

/*
 * [network_config.hpp:__enum__ row]
 *   enum_name   : Protocol
 *   enumerators : 3
 *   hpp_file    : network_config.hpp
 */
enum class Protocol { http = 80, https = 443, ssh = 22 };

template <>
struct iguana::enum_value<LogLevel> {
    constexpr static std::array<int, 4> value = {0, 1, 2, 3};
};

template <>
struct iguana::enum_value<Protocol> {
    constexpr static std::array<int, 3> value = {80, 443, 22};
};



namespace app {

struct ServerConfig {
    /*
     * [sample_config.csv:13]
     *   field_name  : host
     *   group       : ServerConfig
     *   type        : string
     *   default     : 0.0.0.0
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : IP address to bind
     *   hpp_file    : network_config.hpp
     */
    // IP address to bind
    std::string host = "0.0.0.0";
    /*
     * [sample_config.csv:14]
     *   field_name  : port
     *   group       : ServerConfig
     *   type        : int
     *   default     : 8080
     *   min         : 1024
     *   max         : 65535
     *   optional    : false
     *   description : Listening port
     *   hpp_file    : network_config.hpp
     */
    // Listening port
    int32_t port = 8080;
    /*
     * [sample_config.csv:15]
     *   field_name  : backlog
     *   group       : ServerConfig
     *   type        : int
     *   default     : 128
     *   min         : 1
     *   max         : 4096
     *   optional    : false
     *   description : TCP listen backlog
     *   hpp_file    : network_config.hpp
     */
    // TCP listen backlog
    int32_t backlog = 128;
};
YLT_REFL(ServerConfig, host, port, backlog);

struct ConnectionConfig {
    /*
     * [sample_config.csv:16]
     *   field_name  : protocol
     *   group       : ConnectionConfig
     *   type        : Protocol
     *   default     : http
     *   min         : 
     *   max         : 
     *   optional    : false
     *   description : Network protocol
     *   hpp_file    : network_config.hpp
     */
    // Network protocol
    Protocol protocol = Protocol::http;
    /*
     * [sample_config.csv:17]
     *   field_name  : max_connections
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 1000
     *   min         : 1
     *   max         : 100000
     *   optional    : false
     *   description : Max concurrent connections
     *   hpp_file    : network_config.hpp
     */
    // Max concurrent connections
    int32_t max_connections = 1000;
    /*
     * [sample_config.csv:18]
     *   field_name  : timeout_sec
     *   group       : ConnectionConfig
     *   type        : double
     *   default     : 30.0
     *   min         : 0.5
     *   max         : 86400
     *   optional    : false
     *   description : Connection timeout in seconds
     *   hpp_file    : network_config.hpp
     */
    // Connection timeout in seconds
    double timeout_sec = 30.0;
    /*
     * [sample_config.csv:19]
     *   field_name  : cert_file
     *   group       : ConnectionConfig
     *   type        : string
     *   default     : 
     *   min         : 
     *   max         : 
     *   optional    : true
     *   description : TLS certificate file path (optional)
     *   hpp_file    : network_config.hpp
     */
    // TLS certificate file path (optional)
    std::optional<std::string> cert_file;
    /*
     * [sample_config.csv:20]
     *   field_name  : retry_times
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 3
     *   min         : 0
     *   max         : 10
     *   optional    : false
     *   description : Connection retry count
     *   hpp_file    : network_config.hpp
     */
    // Connection retry count
    int32_t retry_times = 3;
    /*
     * [sample_config.csv:21]
     *   field_name  : allowed_ciphers
     *   group       : ConnectionConfig
     *   type        : vector<string>
     *   default     : 
     *   min         : 
     *   max         : 
     *   optional    : true
     *   description : Allowed TLS cipher names (optional)
     *   hpp_file    : network_config.hpp
     */
    // Allowed TLS cipher names (optional)
    std::optional<std::vector<std::string>> allowed_ciphers;
};
YLT_REFL(ConnectionConfig, protocol, max_connections, timeout_sec, cert_file, retry_times, allowed_ciphers);

/// Schema version declared in the CSV __metadata__ row.
constexpr std::string_view kServerConfigSchemaVersion{"1.0.0"};

/// Schema version declared in the CSV __metadata__ row.
constexpr std::string_view kConnectionConfigSchemaVersion{"1.0.0"};

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ServerConfig(const ServerConfig& cfg);

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ConnectionConfig(const ConnectionConfig& cfg);

} // namespace app