#include <sstream>
#include <cassert>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

#include <light_config/light_config.hpp>

/// Sample config struct with a mix of required and optional fields.
struct AppConfig {
    std::string server_host;
    int port = 8080;
    bool debug = false;
    std::optional<std::string> log_file;
    std::optional<int> backlog; 
    std::optional<double> timeout_sec;
    std::optional<int> max_connections;
    std::vector<std::string> allowed_origins;
};
YLT_REFL(AppConfig, server_host, port, debug, log_file, max_connections,
         backlog, timeout_sec, allowed_origins);

int main() {
    // ---- JSON example ----
    const std::string json_content = R"({
        "server_host": "0.0.0.0",
        "port": 443,
        "debug": true,
        "max_connections": 100,
        "allowed_origins": ["https://example.com"]
    })";

    {
        AppConfig cfg;
        auto r = light_config::load_from_json_string(cfg, json_content);
        assert(r.ok());
        assert(cfg.server_host == "0.0.0.0");
        assert(cfg.port == 443);
        assert(cfg.debug == true);
        assert(cfg.max_connections.has_value());
        assert(cfg.max_connections.value() == 100);
        assert(cfg.allowed_origins.size() == 1);

        // log_file was absent from the JSON.
        assert(!cfg.log_file.has_value());
        assert(r.absent_optionals.size() == 3);
        assert(r.absent_optionals[0] == "log_file");
        assert(r.absent_optionals[1] == "backlog");
        assert(r.absent_optionals[2] == "timeout_sec");
        assert(r.present_fields.size() == 5);

        std::cout << "[PASS] JSON: absent optionals detected correctly.\n";
    }

    // ---- YAML example ----
    const std::string yaml_content = R"(
server_host: "0.0.0.0"
port: 443
debug: true
max_connections: 100
allowed_origins:
  - "https://example.com"
)";

    {
        AppConfig cfg;
        auto r = light_config::load_from_yaml_string(cfg, yaml_content);
        assert(r.ok());
        assert(cfg.server_host == "0.0.0.0");
        assert(cfg.port == 443);
        assert(cfg.max_connections.has_value());

        // log_file was absent from YAML -> reported absent.
        assert(r.absent_optionals.size() == 3);
        assert(r.absent_optionals[0] == "log_file");
        assert(r.absent_optionals[1] == "backlog");
        assert(r.absent_optionals[2] == "timeout_sec");

        std::cout << "[PASS] YAML: absent optionals detected correctly.\n";
    }

    // ---- Format auto-detection with file ----
    {
        const std::string tmp_path = "/tmp/light_config_test.json";
        {
            std::ofstream out(tmp_path);
            out << json_content;
        }

        AppConfig cfg;
        auto r = light_config::load(cfg, tmp_path, light_config::Format::Auto);
        assert(r.ok());
        assert(cfg.server_host == "0.0.0.0");
        assert(r.absent_optionals.size() == 3);
        std::cout << "[PASS] Auto-format JSON file: ok.\n";
    }

    // ---- Error code example ----
    {
        AppConfig cfg;
        auto r = light_config::load_from_json_file(cfg, "/nonexistent.json");
        assert(!r.ok());
        assert(r.code == light_config::ErrorCode::kFileReadError);
        assert(!r.message.empty());
        std::cout << "[PASS] Error code: " << static_cast<int>(r.code)
                  << " (" << r.message << ")\n";
    }

    // ---- Range check example using structured errors ----
    {
        const std::string range_json = R"({
            "server_host": "0.0.0.0",
            "port": 8080,
            "debug": false,
            "max_connections": 50000,
            "backlog": 0,
            "timeout_sec": 0.1,
            "allowed_origins": ["https://example.com"]
        })";

        AppConfig cfg;
        auto r = light_config::load_from_json_string(cfg, range_json);
        assert(r.ok());

        // Check range constraints programmatically.
        std::vector<std::string> issues;

        if (cfg.max_connections.has_value()) {
            int v = cfg.max_connections.value();
            if (v < 1 || v > 10000) {
                std::ostringstream oss;
                oss << "max_connections = " << v
                    << " out of range [1, 10000]";
                issues.push_back(oss.str());
            }
        }
        if (cfg.backlog.has_value()) {
            int v = cfg.backlog.value();
            if (v < 1 || v > 4096) {
                std::ostringstream oss;
                oss << "backlog = " << v
                    << " out of range [1, 4096]";
                issues.push_back(oss.str());
            }
        }
        if (cfg.timeout_sec.has_value()) {
            double v = cfg.timeout_sec.value();
            if (v < 0.5 || v > 300.0) {
                std::ostringstream oss;
                oss << "timeout_sec = " << v
                    << " out of range [0.5, 300.0]";
                issues.push_back(oss.str());
            }
        }

        assert(!issues.empty());
        assert(issues.size() == 3);
        std::cout << "[PASS] Range checks produced "
                  << issues.size() << " issues.\n";
    }

    std::cout << "\nAll examples passed.\n";
    return 0;
}
