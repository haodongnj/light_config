#pragma once

/// Auto-generated config struct from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.

#include <light_config/light_config.hpp>
#include <string>
#include <vector>
#include <optional>

struct ServerConfig {
    // IP address to bind
    std::string host = "0.0.0.0";
    // Listening port
    int port = 8080;
    // TCP listen backlog
    int backlog = 128;
};
YLT_REFL(ServerConfig, host, port, backlog);

struct ConnectionConfig {
    // Max concurrent connections
    int max_connections = 1000;
    // Connection timeout in seconds
    double timeout_sec = 30.0;
    // TLS certificate file path (optional)
    std::optional<std::string> cert_file;
};
YLT_REFL(ConnectionConfig, max_connections, timeout_sec, cert_file);

struct AppConfig {
    // Enable debug logging
    bool debug = false;
    // Optional log file path
    std::optional<std::string> log_file;
    // Allowed CORS origins
    std::optional<std::vector<std::string>> allowed_origins;
    ServerConfig server;
    ConnectionConfig connection;
};
YLT_REFL(AppConfig, debug, log_file, allowed_origins, server, connection);

#include <sstream>

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
inline light_config::LoadResult validate_ServerConfig(
    const ServerConfig& cfg) {
    std::vector<std::string> errors;
    if (cfg.port < 1024 || cfg.port > 65535) {
        std::ostringstream oss;
        oss << "port = " << cfg.port << " out of range [1024, 65535]";
        errors.push_back(oss.str());
    }
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
    return light_config::LoadResult::failure(
        light_config::ErrorCode::kValidationError, summary.str());
}


/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
inline light_config::LoadResult validate_ConnectionConfig(
    const ConnectionConfig& cfg) {
    std::vector<std::string> errors;
    if (cfg.max_connections < 1 || cfg.max_connections > 100000) {
        std::ostringstream oss;
        oss << "max_connections = " << cfg.max_connections << " out of range [1, 100000]";
        errors.push_back(oss.str());
    }
    if (cfg.timeout_sec < 0.5 || cfg.timeout_sec > 86400) {
        std::ostringstream oss;
        oss << "timeout_sec = " << cfg.timeout_sec << " out of range [0.5, 86400]";
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
    return light_config::LoadResult::failure(
        light_config::ErrorCode::kValidationError, summary.str());
}


/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
inline light_config::LoadResult validate_AppConfig(
    const AppConfig& cfg) {
    std::vector<std::string> errors;
    {
        auto r = validate_ServerConfig(cfg.server);
        if (!r.ok()) {
            errors.push_back("server: " + r.message);
        }
    }
    {
        auto r = validate_ConnectionConfig(cfg.connection);
        if (!r.ok()) {
            errors.push_back("connection: " + r.message);
        }
    }
    if (errors.empty()) {
        return light_config::LoadResult::success();
    }

    std::ostringstream summary;
    summary << errors.size() << " validation error(s)";
    for (const auto& e : errors) {
        summary << "\n  " << e;
    }
    return light_config::LoadResult::failure(
        light_config::ErrorCode::kValidationError, summary.str());
}

