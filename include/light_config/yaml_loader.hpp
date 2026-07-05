#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_yaml/yaml_reader.h>
#include <ylt/struct_yaml/yaml_writer.h>

#include <exception>

#include "light_config/detail/audit_yaml.hpp"
#include "light_config/detail/file_utils.hpp"
#include "light_config/result.hpp"
#include <fstream>

namespace light_config {

/// Load a YAML config file into a struct and report optional-field presence.
///
/// YAML limitation: iguana has no YAML DOM API, so absent-vs-null detection
/// is not possible. All std::optional fields that end up std::nullopt after
/// loading are reported as absent (which includes fields explicitly set to
/// null in the YAML).
///
/// Nested structs (with YLT_REFL) are recursively audited with
/// dot-separated field paths.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the YAML file.
/// \return     Result with code==kOk and field audit on success.
template <typename T>
Result load_from_yaml_file(T& config, const std::string& path) {
    // Read file content.
    std::string content;
    if (auto r = detail::read_file_into_string(path, content); !r.ok()) {
        return r;
    }

    // Load the struct from YAML.
    try {
        iguana::from_yaml(config, content);
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kYamlParseError, e.what());
    }

    auto result = Result::success();

    // Recursive audit of optional fields.
    detail::audit_yaml_recursive(config, result.absent_optionals, result.present_fields);

    return result;
}

/// Load a YAML string into a struct with optional-field audit.
template <typename T>
Result load_from_yaml_string(T& config, const std::string& yaml_str) {
    try {
        iguana::from_yaml(config, yaml_str);
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kYamlParseError, e.what());
    }

    auto result = Result::success();

    detail::audit_yaml_recursive(config, result.absent_optionals, result.present_fields);

    return result;
}

/// Load a YAML string with optional schema version check.
///
/// YAML limitation: iguana 0.6.1 has no YAML DOM, so the version check is a
/// simple substring search for `$schema:` in the raw content.  It handles the
/// common case (unquoted scalar on its own line) but not quoted strings or
/// flow-style mappings.  For strict checking, use the JSON format.
template <typename T>
Result load_from_yaml_string(T& config, const std::string& yaml_str,
                             std::string_view expected_schema_version) {
    if (!expected_schema_version.empty()) {
        // Best-effort check: look for `$schema: <value>` on a line.
        auto pos = yaml_str.find("$schema:");
        if (pos != std::string::npos) {
            auto val_start = yaml_str.find_first_not_of(" \t", pos + 8);
            if (val_start != std::string::npos) {
                auto val_end = yaml_str.find_first_of("\r\n", val_start);
                auto found_ver = yaml_str.substr(val_start, val_end - val_start);
                // Trim trailing whitespace.
                auto trim_end = found_ver.find_last_not_of(" \t");
                if (trim_end != std::string::npos) {
                    found_ver = found_ver.substr(0, trim_end + 1);
                }
                if (found_ver != expected_schema_version) {
                    auto msg = std::string("expected schema version '")
                               + std::string(expected_schema_version) + "' but file has '"
                               + found_ver + "'";
                    return Result::failure(ErrorCode::kSchemaMismatch, std::move(msg));
                }
            }
        }
        // $schema absent → no error (permissive)
    }

    // Delegate to the existing (non-checking) implementation.
    return load_from_yaml_string(config, yaml_str);
}

/// Load a YAML file with optional schema version check.
template <typename T>
Result load_from_yaml_file(T& config, const std::string& path,
                           std::string_view expected_schema_version) {
    // Read file content.
    std::string content;
    if (auto r = detail::read_file_into_string(path, content); !r.ok()) {
        return r;
    }

    return load_from_yaml_string(config, content, expected_schema_version);
}

/// Serialize a config struct to a YAML string.
///
/// Uses iguana::to_yaml with min_spaces=0 for top-level fields.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[in] config  The config struct to serialize.
/// \return  The YAML string, or std::nullopt if serialization throws.
template <typename T>
std::optional<std::string> to_yaml(const T& config) {
    try {
        std::string ss;
        iguana::to_yaml(config, ss, 0);
        return ss;
    } catch (const std::exception&) {
        // Defensive: iguana serialization does not throw for well-formed
        // YLT_REFL-annotated structs. This catch exists to uphold the API
        // contract (never throw from a load/save function) against
        // hypothetical edge cases (bad_alloc, corrupted internal state).
        // This path is intentionally uncovered by tests.
        return std::nullopt;
    }
}

/// Write a config struct to a YAML file.
///
/// Serializes the struct and writes it to the given path. The file is
/// truncated if it already exists.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[in] config  The config struct to serialize.
/// \param[in] path    Path to the output YAML file.
/// \return  Result with code==kOk on success; kYamlSerializeError or
///          kFileWriteError on failure.
template <typename T>
Result save_to_yaml_file(const T& config, const std::string& path) {
    auto yaml_opt = to_yaml(config);
    if (!yaml_opt.has_value()) {
        return Result::failure(ErrorCode::kYamlSerializeError,
                               "failed to serialize config to YAML");
    }
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) {
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    file << yaml_opt.value();
    file.close();
    if (!file.good()) {
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    return Result::success();
}

}  // namespace light_config
