/// Auto-generated validation implementations from CSV schema.
/// DO NOT EDIT BY HAND — regenerate with scripts/gen_config.py.
///
/// --- Schema provenance ---
///   schema_version : 1.0.0
///   source_csv     : sample_config.csv
///   csv_md5        : 9bd084c1c88cb838bf8cd819e637de54
///   generated_at   : 2026-07-05T02:25:23.039203+00:00
///   generator      : light_config
/// -----------------------

#include "app_config.hpp"

#include <sstream>

namespace app {

light_config::LoadResult validate_AppConfig(const AppConfig& cfg) {
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
    return light_config::LoadResult::failure(light_config::ErrorCode::kValidationError,
                                             summary.str());
}

}  // namespace app