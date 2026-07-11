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

/// Detect format from file extension.
///
/// `.yaml` / `.yml` → YAML; `.json` → JSON; no extension → JSON (default);
/// anything else → Auto (caller should return kUnrecognizedFormat).
/// Extension matching is case-insensitive (`.YAML`, `.JSON`, `.Yml` all
/// recognized) — REVIEW.md H3.
inline Format detect_format(const std::string& path) {
    auto dot = path.rfind('.');
    if (dot == std::string::npos)
        return Format::Json;  // no extension
    // Lowercase the extension (ASCII) for case-insensitive comparison.
    std::string ext;
    ext.reserve(path.size() - dot);
    for (size_t i = dot; i < path.size(); ++i) {
        char c = path[i];
        ext.push_back(c >= 'A' && c <= 'Z' ? static_cast<char>(c - 'A' + 'a') : c);
    }
    if (ext == ".yaml" || ext == ".yml")
        return Format::Yaml;
    if (ext == ".json")
        return Format::Json;
    return Format::Auto;  // unrecognized extension
}

/// Infer format from file extension and load the config.
///
/// `.yaml` / `.yml` → YAML; `.json` → JSON; unrecognized extension →
/// kUnrecognizedFormat error.
template <typename T>
Result load(T& config, const std::string& path, Format format = Format::Auto) {
    if (format == Format::Auto) {
        format = detect_format(path);
    }
    if (format == Format::Auto) {
        return Result::failure(ErrorCode::kUnrecognizedFormat,
                               "cannot determine format from file extension '" + path + "'");
    }
    if (format == Format::Yaml) {
        return load_from_yaml_file(config, path);
    }
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
Result load_versioned(T& config, const std::string& path, std::string_view expected_schema_version,
                      Format format = Format::Auto) {
    if (format == Format::Auto) {
        format = detect_format(path);
    }
    if (format == Format::Auto) {
        return Result::failure(ErrorCode::kUnrecognizedFormat,
                               "cannot determine format from file extension '" + path + "'");
    }
    if (format == Format::Yaml) {
        return load_from_yaml_file(config, path, expected_schema_version);
    }
    return load_from_json_file(config, path, expected_schema_version);
}

}  // namespace light_config
