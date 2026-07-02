#pragma once

/// light_config – Minimal C++17 config-file loader built on yalantinglib.
///
/// Usage:
///   struct MyConfig { int port; std::optional<std::string> host; };
///   YLT_REFL(MyConfig, port, host);
///
///   MyConfig cfg;
///   auto r = light_config::load(cfg, "config.json");
///   if (!r.ok) { /* handle r.error */ }
///   // r.absent_optionals lists std::optional fields missing from file.

#include <string>

#include "light_config/json_loader.hpp"
#include "light_config/yaml_loader.hpp"

namespace light_config {

/// Infer format from file extension and load the config.
///
/// `.yaml` / `.yml` → YAML; anything else → JSON.
template <typename T>
LoadResult load(T& config, const std::string& path, Format format = Format::Auto) {
    if (format == Format::Yaml) {
        return load_from_yaml_file(config, path);
    }
    if (format == Format::Json) {
        return load_from_json_file(config, path);
    }

    // Format::Auto – detect from suffix.
    auto dot = path.rfind('.');
    if (dot != std::string::npos) {
        auto ext = path.substr(dot);
        if (ext == ".yaml" || ext == ".yml") {
            return load_from_yaml_file(config, path);
        }
    }
    // Default to JSON.
    return load_from_json_file(config, path);
}

/// Load with schema version enforcement.
///
/// When \p expected_schema_version is non-empty, the loader checks the
/// `"$schema"` key in JSON configs (or post-load for YAML) and returns
/// kSchemaMismatch on mismatch.  The permissive default (empty string)
/// preserves backward compatibility — existing callers that don't use
/// schema versioning are unaffected.
template <typename T>
LoadResult load_versioned(T& config, const std::string& path,
                          std::string_view expected_schema_version,
                          Format format = Format::Auto) {
    if (format == Format::Yaml) {
        return load_from_yaml_file(config, path, expected_schema_version);
    }
    if (format == Format::Json) {
        return load_from_json_file(config, path, expected_schema_version);
    }

    // Format::Auto
    auto dot = path.rfind('.');
    if (dot != std::string::npos) {
        auto ext = path.substr(dot);
        if (ext == ".yaml" || ext == ".yml") {
            return load_from_yaml_file(config, path, expected_schema_version);
        }
    }
    return load_from_json_file(config, path, expected_schema_version);
}

}  // namespace light_config
