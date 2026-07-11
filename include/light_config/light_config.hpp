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
/// recognized).
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
[[nodiscard]] Result load(T& config, const std::string& path, Format format = Format::Auto) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

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

/// Infer format from file extension, load the config, and run a validator.
///
/// Combines load() and validation into a single call so that forgetting
/// validation is not possible.  If loading fails the load error is returned
/// without calling the validator.  If loading succeeds, the validator is
/// invoked on the populated config; a validation failure is returned as
/// kValidationError, otherwise the load result (with audit info) is returned.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \tparam Validator  Callable accepting `const T&` and returning Result
///                    (e.g. generated validate_AppConfig).
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the config file (JSON or YAML).
/// \param[in]  validator  Validation function.
/// \param[in]  format  Expected format (Auto detects from extension).
/// \return     Result with code==kOk, field audit, and validation pass.
template <typename T, typename Validator>
[[nodiscard]] Result load_and_validate(T& config, const std::string& path, Validator&& validator,
                                       Format format = Format::Auto) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    if (format == Format::Auto) {
        format = detect_format(path);
    }
    if (format == Format::Auto) {
        return Result::failure(ErrorCode::kUnrecognizedFormat,
                               "cannot determine format from file extension '" + path + "'");
    }
    if (format == Format::Yaml) {
        return load_from_yaml_file_and_validate(config, path, std::forward<Validator>(validator));
    }
    return load_from_json_file_and_validate(config, path, std::forward<Validator>(validator));
}

/// Load with schema version enforcement.
///
/// When \p expected_schema_version is non-empty, the loader checks the
/// `"$schema"` key in JSON configs (or post-load for YAML) and returns
/// kSchemaMismatch on mismatch.  The permissive default (empty string)
/// preserves backward compatibility — existing callers that don't use
/// schema versioning are unaffected.
template <typename T>
[[nodiscard]] Result load_versioned(T& config, const std::string& path,
                                    std::string_view expected_schema_version,
                                    Format format = Format::Auto) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

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

/// Load with schema version enforcement, then run a validator.
///
/// Combines load_versioned() and validation into a single call.  If loading
/// or schema check fails the error is returned without calling the validator.
/// If loading succeeds, the validator is invoked on the populated config;
/// a validation failure is returned as kValidationError, otherwise the load
/// result (with audit info) is returned.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \tparam Validator  Callable accepting `const T&` and returning Result
///                    (e.g. generated validate_AppConfig).
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the config file (JSON or YAML).
/// \param[in]  expected_schema_version  Required schema version.
/// \param[in]  validator  Validation function.
/// \param[in]  format  Expected format (Auto detects from extension).
/// \return     Result with code==kOk, field audit, and validation pass.
template <typename T, typename Validator>
[[nodiscard]] Result load_versioned_and_validate(T& config, const std::string& path,
                                                 std::string_view expected_schema_version,
                                                 Validator&& validator,
                                                 Format format = Format::Auto) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    if (format == Format::Auto) {
        format = detect_format(path);
    }
    if (format == Format::Auto) {
        return Result::failure(ErrorCode::kUnrecognizedFormat,
                               "cannot determine format from file extension '" + path + "'");
    }
    if (format == Format::Yaml) {
        return load_from_yaml_file_and_validate(config, path, std::forward<Validator>(validator),
                                                expected_schema_version);
    }
    return load_from_json_file_and_validate(config, path, std::forward<Validator>(validator),
                                            expected_schema_version);
}

}  // namespace light_config
