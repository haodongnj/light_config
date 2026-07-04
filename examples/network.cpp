/// Auto-generated validation implementations from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.
///
/// --- Schema provenance ---
///   schema_version : 1.0.0
///   source_csv     : sample_config.csv
///   csv_md5        : a75c3b990d9070d6b5e7a3dd8ec5bb60
///   generated_at   : 2026-07-04T10:16:12.761500+00:00
///   generator      : light_config
/// -----------------------

#include "network.hpp"

#include <sstream>

namespace app {

light_config::LoadResult validate_ServerConfig(const ServerConfig& cfg) {
    std::vector<std::string> errors;
    /*
     * [sample_config.csv:11]
     *   field_name  : port
     *   group       : ServerConfig
     *   type        : int
     *   default     : 8080
     *   min         : 1024
     *   max         : 65535
     *   optional    : false
     *   description : Listening port
     *   hpp_file    : network.hpp
     */
    if (cfg.port < 1024 || cfg.port > 65535) {
        std::ostringstream oss;
        oss << "port = " << cfg.port << " out of range [1024, 65535]";
        errors.push_back(oss.str());
    }
    /*
     * [sample_config.csv:12]
     *   field_name  : backlog
     *   group       : ServerConfig
     *   type        : int
     *   default     : 128
     *   min         : 1
     *   max         : 4096
     *   optional    : false
     *   description : TCP listen backlog
     *   hpp_file    : network.hpp
     */
    if (cfg.backlog < 1 || cfg.backlog > 4096) {
        std::ostringstream oss;
        oss << "backlog = " << cfg.backlog << " out of range [1, 4096]";
        errors.push_back(oss.str());
    }
    if (errors.empty()) {
        return light_config::LoadResult::success();
    }

    std::ostringstream summary;
    summary << errors.size() << " validation error(s)";
    for (const auto& e : errors) {
        summary << "\n  " << e;
    }
    return light_config::LoadResult::failure(light_config::ErrorCode::kValidationError,
                                             summary.str());
}

light_config::LoadResult validate_ConnectionConfig(const ConnectionConfig& cfg) {
    std::vector<std::string> errors;
    /*
     * [sample_config.csv:13]
     *   field_name  : max_connections
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 1000
     *   min         : 1
     *   max         : 100000
     *   optional    : false
     *   description : Max concurrent connections
     *   hpp_file    : network.hpp
     */
    if (cfg.max_connections < 1 || cfg.max_connections > 100000) {
        std::ostringstream oss;
        oss << "max_connections = " << cfg.max_connections << " out of range [1, 100000]";
        errors.push_back(oss.str());
    }
    /*
     * [sample_config.csv:14]
     *   field_name  : timeout_sec
     *   group       : ConnectionConfig
     *   type        : double
     *   default     : 30.0
     *   min         : 0.5
     *   max         : 86400
     *   optional    : false
     *   description : Connection timeout in seconds
     *   hpp_file    : network.hpp
     */
    if (cfg.timeout_sec < 0.5 || cfg.timeout_sec > 86400) {
        std::ostringstream oss;
        oss << "timeout_sec = " << cfg.timeout_sec << " out of range [0.5, 86400]";
        errors.push_back(oss.str());
    }
    /*
     * [sample_config.csv:16]
     *   field_name  : retry_times
     *   group       : ConnectionConfig
     *   type        : int
     *   default     : 3
     *   min         : 0
     *   max         : 10
     *   optional    : false
     *   description : Connection retry count
     *   hpp_file    : network.hpp
     */
    if (cfg.retry_times < 0 || cfg.retry_times > 10) {
        std::ostringstream oss;
        oss << "retry_times = " << cfg.retry_times << " out of range [0, 10]";
        errors.push_back(oss.str());
    }
    if (errors.empty()) {
        return light_config::LoadResult::success();
    }

    std::ostringstream summary;
    summary << errors.size() << " validation error(s)";
    for (const auto& e : errors) {
        summary << "\n  " << e;
    }
    return light_config::LoadResult::failure(light_config::ErrorCode::kValidationError,
                                             summary.str());
}

}  // namespace app