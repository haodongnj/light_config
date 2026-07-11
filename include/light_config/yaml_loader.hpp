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
[[nodiscard]] Result load_from_yaml_file(T& config, const std::string& path) {
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
[[nodiscard]] Result load_from_yaml_string(T& config, const std::string& yaml_str) {
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
/// line-by-line scan for `$schema:` at the start of a line's content (after
/// optional indentation).  Line-leading `#` comments are skipped.  Mid-line
/// comments (e.g. `name: x # $schema: 2.0.0`) are out of scope.  For strict
/// checking, use the JSON format.
template <typename T>
[[nodiscard]] Result load_from_yaml_string(T& config, const std::string& yaml_str,
                                           std::string_view expected_schema_version) {
    if (!expected_schema_version.empty()) {
        // Line-aware scan: the old raw find("$schema:")
        // matched inside # comments.  Walk lines, skip line-leading
        // comments, and match $schema: only at the start of the line's
        // content.  This is NOT a full YAML parser — mid-line comments
        // are out of scope.
        bool found = false;
        std::string found_ver;
        size_t pos = 0;
        while (pos < yaml_str.size()) {
            auto line_end = yaml_str.find_first_of("\r\n", pos);
            if (line_end == std::string::npos)
                line_end = yaml_str.size();
            std::string_view line(yaml_str.data() + pos, line_end - pos);
            // First non-space char of the line.
            auto first_ns = line.find_first_not_of(" \t");
            if (first_ns != std::string_view::npos && line[first_ns] == '#') {
                // line-leading comment — skip.
            } else if (first_ns != std::string_view::npos
                       && line.substr(first_ns).rfind("$schema:", 0) == 0) {
                // $schema: at the start of the content.
                auto val_start = first_ns + 8;  // length of "$schema:"
                auto lv = line.substr(val_start);
                auto vs = lv.find_first_not_of(" \t");
                if (vs != std::string_view::npos) {
                    lv = lv.substr(vs);
                    // Trim trailing whitespace.
                    auto ve = lv.find_last_not_of(" \t");
                    if (ve != std::string_view::npos)
                        lv = lv.substr(0, ve + 1);
                    // Strip one surrounding pair of " or '.
                    if (lv.size() >= 2) {
                        char f = lv.front(), l = lv.back();
                        if ((f == '"' && l == '"') || (f == '\'' && l == '\''))
                            lv = lv.substr(1, lv.size() - 2);
                    }
                    found = true;
                    found_ver = std::string(lv);
                }
            }
            // Advance past this line's terminator.
            pos = line_end;
            while (pos < yaml_str.size() && (yaml_str[pos] == '\r' || yaml_str[pos] == '\n'))
                ++pos;
            if (found)
                break;
        }
        if (found && found_ver != expected_schema_version) {
            auto msg = std::string("expected schema version '")
                       + std::string(expected_schema_version) + "' but file has '" + found_ver
                       + "'";
            return Result::failure(ErrorCode::kSchemaMismatch, std::move(msg));
        }
        // $schema absent (or comment-only) -> permissive, no error.
    }

    // Delegate to the existing (non-checking) implementation.
    return load_from_yaml_string(config, yaml_str);
}

/// Load a YAML file with optional schema version check.
template <typename T>
[[nodiscard]] Result load_from_yaml_file(T& config, const std::string& path,
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
/// \param[out] err_msg  If non-null and serialization throws, filled with the
///             exception's what() message (so callers can surface a real
///             diagnostic instead of a generic "failed to serialize").
/// \return  The YAML string, or std::nullopt if serialization throws.
template <typename T>
std::optional<std::string> to_yaml(const T& config, std::string* err_msg = nullptr) {
    try {
        std::string ss;
        iguana::to_yaml(config, ss, 0);
        return ss;
    } catch (const std::exception& e) {
        // Defensive: iguana serialization does not throw for well-formed
        // YLT_REFL-annotated structs. This catch exists to uphold the API
        // contract (never throw from a load/save function) against
        // hypothetical edge cases (bad_alloc, corrupted internal state).
        // Surface the exception message so a real failure here is debuggable
        // instead of presenting as a bare "failed to serialize" string.
        if (err_msg) {
            *err_msg = e.what();
        }
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
[[nodiscard]] Result save_to_yaml_file(const T& config, const std::string& path) {
    std::string serialize_err;
    auto yaml_opt = to_yaml(config, &serialize_err);
    if (!yaml_opt.has_value()) {
        // Surface the underlying exception message (if any) so a real
        // serialization failure is debuggable instead of a bare string.
        std::string msg = "failed to serialize config to YAML";
        if (!serialize_err.empty()) {
            msg += ": ";
            msg += serialize_err;
        }
        return Result::failure(ErrorCode::kYamlSerializeError, std::move(msg));
    }
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) {
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    file << yaml_opt.value();
    // Detect a failed write *before* close.  See save_to_json_file for the
    // rationale: operator<< on a buffered ofstream can return having only
    // buffered the bytes; a disk-full or I/O error surfaces when the buffer
    // is flushed.  We force the flush explicitly and inspect failbit/badbit
    // — checking good() *after* close is unreliable (good() is also false
    // when eofbit is set).
    file.flush();
    if (file.fail()) {
        file.close();
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    file.close();
    if (!file) {
        // A failure surfaced during close itself (e.g. flush-on-close).
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    return Result::success();
}

}  // namespace light_config
