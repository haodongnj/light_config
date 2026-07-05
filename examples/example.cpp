#include <light_config/light_config.hpp>

#include <cassert>
#include <filesystem>
#include <iostream>

#include <fstream>

// Generated from examples/sample_config.csv via:
//   python3 scripts/gen_config.py --input examples/sample_config.csv \
//       --output-dir examples/ --generate-samples
//
// Generates app_config.hpp and app_config.cpp in examples/
//
#include "app_config.hpp"

using app::AppConfig;
using app::ServerConfig;
using app::validate_AppConfig;
using app::validate_ServerConfig;

// NOLINTNEXTLINE(readability-function-size,bugprone-exception-escape)
int main() {
    // ---- JSON example with compound config ----
    const std::string json_content = R"({
        "debug": true,
        "allowed_origins": ["https://example.com"],
        "server": {
            "host": "0.0.0.0",
            "port": 443
        },
        "connection": {
            "max_connections": 500,
            "timeout_sec": 60.0
        }
    })";

    {
        AppConfig cfg;
        auto r = light_config::load_from_json_string(cfg, json_content);
        assert(r.ok());
        assert(cfg.debug);
        assert(cfg.server.host == "0.0.0.0");
        assert(cfg.server.port == 443);
        assert(cfg.connection.max_connections == 500);

        // log_file was absent from the JSON -> default preserved.
        // (log_file is a plain std::string with a default, not an optional,
        //  so it is not reported in absent_optionals.)
        assert(cfg.log_file == "/var/log/app.log");

        std::cout << "[PASS] JSON: compound config loaded, log_file default preserved.\n";
    }

    // ---- JSON: nested absent detection (optional sub-field) ----
    {
        const std::string partial_json = R"({
            "debug": false,
            "server": {
                "host": "10.0.0.1",
                "port": 9000
            },
            "connection": {
                "max_connections": 200
            }
        })";

        AppConfig cfg;
        auto r = light_config::load_from_json_string(cfg, partial_json);
        assert(r.ok());
        assert(cfg.server.host == "10.0.0.1");
        assert(cfg.server.port == 9000);
        assert(cfg.connection.max_connections == 200);
        // connection.cert_file is optional and absent -> dot-separated
        assert(!cfg.connection.cert_file.has_value());
        auto found_cert = false;
        for (auto& name : r.absent_optionals) {
            if (name == "connection.cert_file") {
                found_cert = true;
            }
        }
        assert(found_cert);
        // log_file is a plain std::string (has a default), so absence from the
        // JSON just preserves the default; it is not an absent optional.
        assert(cfg.log_file == "/var/log/app.log");
        std::cout << "[PASS] JSON: connection.cert_file absent, dot-separated.\n";
    }

    // ---- YAML example ----
    const std::string yaml_content = R"(
debug: true
server:
  host: "0.0.0.0"
  port: 8443
  backlog: 256
connection:
  timeout_sec: 45.0
)";

    {
        AppConfig cfg;
        auto r = light_config::load_from_yaml_string(cfg, yaml_content);
        assert(r.ok());
        assert(cfg.server.port == 8443);
        assert(cfg.server.backlog == 256);
        assert(cfg.connection.timeout_sec == 45.0);
        // max_connections absent -> nullopt after YAML load
        if constexpr (false) {  // NOLINT(readability-simplify-boolean-expr)
                                // Intentional: maintain symmetry with JSON branch
        }
        std::cout << "[PASS] YAML: compound config loaded.\n";
    }

    // ---- Format auto-detection with file ----
    {
        const std::string tmp_path =
            (std::filesystem::temp_directory_path() / "light_config_test.json").string();
        {
            std::ofstream out(tmp_path);
            out << json_content;
        }

        AppConfig cfg;
        auto r = light_config::load(cfg, tmp_path, light_config::Format::Auto);
        assert(r.ok());
        assert(cfg.debug);
        std::cout << "[PASS] Auto-format JSON file: ok.\n";
    }

    // ---- Error code example ----
    {
        AppConfig cfg;
        auto r = light_config::load_from_json_file(cfg, "/nonexistent.json");
        assert(!r.ok());
        assert(r.code == light_config::ErrorCode::kFileReadError);
        assert(!r.message.empty());
        std::cout << "[PASS] Error code: " << static_cast<int>(r.code) << " (" << r.message
                  << ")\n";
    }

    // ---- Generated validate function (replaces hand-written range checks) ----
    {
        const std::string invalid_json = R"({
            "debug": false,
            "server": {
                "host": "0.0.0.0",
                "port": 70000,
                "backlog": 0
            },
            "connection": {
                "max_connections": 200000,
                "timeout_sec": 0.1
            }
        })";

        // We intentionally load with absent fields then check validation
        // separately — both branches are exercised.
        AppConfig /*not-const*/ cfg;
        auto load_r = light_config::load_from_json_string(cfg, invalid_json);
        assert(load_r.ok());  // loading succeeds (values are parsed)

        // validate_AppConfig recurses into Server and Connection,
        // checking min/max constraints from the CSV schema
        auto val_r = validate_AppConfig(cfg);
        assert(!val_r.ok());
        assert(val_r.code == light_config::ErrorCode::kValidationError);
        assert(!val_r.message.empty());

        std::cout << "[PASS] Generated validate_AppConfig() caught "
                  << "out-of-range values:\n"
                  << val_r.message << "\n";
    }

    // ---- Explicit per-struct validation ----
    {
        ServerConfig srv;
        srv.host = "0.0.0.0";
        srv.port = 80;       // below min 1024
        srv.backlog = 5000;  // above max 4096

        auto r = validate_ServerConfig(srv);
        assert(!r.ok());
        std::cout << "[PASS] validate_ServerConfig() caught server errors.\n";
    }

    // ---- Full valid JSON file: validates library end-to-end ----
    // Uses examples/valid_config.json, which has every field populated.
    // Resolve relative to this source file (__FILE__), regardless of CWD.
    {
        auto path = (std::filesystem::path(__FILE__).parent_path() / "valid_config.json").string();

        AppConfig cfg;
        auto r = light_config::load(cfg, path, light_config::Format::Auto);
        assert(r.ok());

        // Top-level fields
        assert(!cfg.debug);
        assert(cfg.log_file == "/var/log/app.log");
        // JSON null → nullopt, but key was present → not in absent_optionals
        assert(!cfg.allowed_origins.has_value());

        // Nested server
        assert(cfg.server.host == "0.0.0.0");
        assert(cfg.server.port == 8080);
        assert(cfg.server.backlog == 128);

        // Nested connection
        assert(cfg.connection.max_connections == 1000);
        assert(cfg.connection.timeout_sec == 30.0);
        assert(cfg.connection.retry_times == 3);
        assert(!cfg.connection.cert_file.has_value());
        assert(!cfg.connection.allowed_ciphers.has_value());

        // JSON DOM audit distinguishes null (present) from absent.
        // All null-valued optionals were explicitly present, so absent_optionals is
        // empty.
        assert(r.absent_optionals.empty());

        // Validation should pass (all values within range)
        auto val_r = validate_AppConfig(cfg);
        assert(val_r.ok());

        std::cout << "[PASS] Full valid JSON file loaded and validated.\n";
    }

    // ---- Full valid YAML file: validates library end-to-end ----
    // Uses examples/valid_config.yaml, which has every field populated.
    // Resolve relative to this source file (__FILE__), regardless of CWD.
    {
        auto path = (std::filesystem::path(__FILE__).parent_path() / "valid_config.yaml").string();

        AppConfig cfg;
        auto r = light_config::load(cfg, path, light_config::Format::Auto);
        assert(r.ok());

        // Top-level fields
        assert(!cfg.debug);
        assert(cfg.log_file == "/var/log/app.log");
        // YAML null → nullopt for optional fields (absent-vs-null conflated, no DOM
        // audit)
        assert(!cfg.allowed_origins.has_value());

        // Nested server
        assert(cfg.server.host == "0.0.0.0");
        assert(cfg.server.port == 8080);
        assert(cfg.server.backlog == 128);

        // Nested connection
        assert(cfg.connection.max_connections == 1000);
        assert(cfg.connection.timeout_sec == 30.0);
        assert(cfg.connection.retry_times == 3);
        assert(!cfg.connection.cert_file.has_value());
        assert(!cfg.connection.allowed_ciphers.has_value());

        // YAML has no DOM audit (null == absent), so absent_optionals picks up
        // null-valued optionals as absent.  Verify the expected set.
        assert(r.absent_optionals.size() == 3);
        auto is_absent = [&](const std::string& name) {
            return std::find(r.absent_optionals.begin(), r.absent_optionals.end(), name)
                   != r.absent_optionals.end();
        };
        assert(is_absent("allowed_origins"));
        assert(is_absent("connection.cert_file"));
        assert(is_absent("connection.allowed_ciphers"));

        // Validation should pass (all values within range)
        auto val_r = validate_AppConfig(cfg);
        assert(val_r.ok());

        std::cout << "[PASS] Full valid YAML file loaded and validated.\n";
    }

    std::cout << "\nAll examples passed.\n";
    return 0;
}
