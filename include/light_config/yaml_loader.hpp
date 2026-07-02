#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_yaml/yaml_reader.h>

#include <cstdint>
#include <exception>
#include <system_error>

#include "light_config/load_result.hpp"
#include <fstream>

namespace light_config {
namespace detail {

/// Recursively audit optional fields in a struct after YAML loading.
/// Uses ylt::reflection::for_each and recurses into members that have
/// YLT_REFL. prefix is the dot-joined parent path.
template <typename T>
void audit_yaml_recursive(const T& obj, std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          const std::string& prefix = "") {
    ylt::reflection::for_each(obj, [&](auto& member, std::string_view name, auto /*index*/) {
        std::string full_name =
            prefix.empty() ? std::string(name) : prefix + "." + std::string(name);

        using field_t = std::decay_t<decltype(member)>;

        if constexpr (is_optional_v<field_t>) {
            if (member.has_value()) {
                present_fields.push_back(full_name);
            } else {
                absent_optionals.push_back(full_name);
            }
        } else {
            present_fields.push_back(full_name);
        }

        // Recurse into nested struct members with YLT_REFL
        if constexpr (ylt::reflection::is_ylt_refl_v<field_t>) {
            audit_yaml_recursive(member, absent_optionals, present_fields, full_name);
        }
    });
}

}  // namespace detail

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
/// \return     LoadResult with code==kOk and field audit on success.
template <typename T>
LoadResult load_from_yaml_file(T& config, const std::string& path) {
    // Read file content.
    std::string content;
    {
        std::error_code ec;
        auto size = std::filesystem::file_size(path, ec);
        if (ec) {
            return LoadResult::failure(ErrorCode::kFileReadError, ec.message());
        }
        if (size == 0) {
            return LoadResult::failure(ErrorCode::kFileEmpty, path);
        }
        content.resize(size);
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            return LoadResult::failure(ErrorCode::kFileReadError, path);
        }
        file.read(content.data(), size);
    }

    // Load the struct from YAML.
    try {
        iguana::from_yaml(config, content);
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kYamlParseError, e.what());
    }

    auto result = LoadResult::success();

    // Recursive audit of optional fields.
    detail::audit_yaml_recursive(config, result.absent_optionals, result.present_fields);

    return result;
}

/// Load a YAML string into a struct with optional-field audit.
template <typename T>
LoadResult load_from_yaml_string(T& config, const std::string& yaml_str) {
    try {
        iguana::from_yaml(config, yaml_str);
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kYamlParseError, e.what());
    }

    auto result = LoadResult::success();

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
LoadResult load_from_yaml_string(T& config, const std::string& yaml_str,
                                 std::string_view expected_schema_version) {
    if (!expected_schema_version.empty()) {
        // Best-effort check: look for `$schema: <value>` on a line.
        auto pos = yaml_str.find("$schema:");
        if (pos != std::string::npos) {
            auto val_start = yaml_str.find_first_not_of(" \t", pos + 8);
            if (val_start != std::string::npos) {
                auto val_end = yaml_str.find_first_of("\r\n", val_start);
                auto found_ver =
                    yaml_str.substr(val_start, val_end - val_start);
                // Trim trailing whitespace.
                auto trim_end = found_ver.find_last_not_of(" \t");
                if (trim_end != std::string::npos) {
                    found_ver = found_ver.substr(0, trim_end + 1);
                }
                if (found_ver != expected_schema_version) {
                    auto msg = std::string("expected schema version '")
                        + std::string(expected_schema_version)
                        + "' but file has '" + found_ver + "'";
                    return LoadResult::failure(ErrorCode::kSchemaMismatch,
                                               std::move(msg));
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
LoadResult load_from_yaml_file(T& config, const std::string& path,
                               std::string_view expected_schema_version) {
    // Read file content.
    std::string content;
    {
        std::error_code ec;
        auto size = std::filesystem::file_size(path, ec);
        if (ec) {
            return LoadResult::failure(ErrorCode::kFileReadError, ec.message());
        }
        if (size == 0) {
            return LoadResult::failure(ErrorCode::kFileEmpty, path);
        }
        content.resize(size);
        std::ifstream file(path, std::ios::binary);
        if (!file) {
            return LoadResult::failure(ErrorCode::kFileReadError, path);
        }
        file.read(content.data(), size);
    }

    return load_from_yaml_string(config, content, expected_schema_version);
}

}  // namespace light_config
