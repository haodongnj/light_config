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

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ServerConfig(const ServerConfig& cfg);

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_ConnectionConfig(const ConnectionConfig& cfg);

/// Validate range constraints defined in the CSV schema.
/// Returns light_config::ErrorCode::kOk on success,
/// kValidationError with detail on failure.
light_config::LoadResult validate_AppConfig(const AppConfig& cfg);
