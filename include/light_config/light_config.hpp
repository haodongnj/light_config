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

}  // namespace light_config
