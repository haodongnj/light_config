#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_json/json_reader.h>
#include <ylt/struct_json/json_writer.h>

#include <exception>

#include "light_config/detail/audit_json.hpp"
#include "light_config/detail/file_utils.hpp"
#include "light_config/result.hpp"
#include <fstream>

namespace light_config {

/// Load a JSON config file into a struct and report optional-field presence.
///
/// The JSON is parsed once into a DOM to audit optional keys, and
/// once to populate the struct. Nested structs (with YLT_REFL) are
/// recursively audited, with dot-separated field paths in the result.
///
/// When \p expected_schema_version is non-empty, the loader checks for a
/// `"$schema"` key at the top level of the JSON object.  If present and its
/// string value does not match the expected version, the result is
/// kSchemaMismatch.  If `"$schema"` is absent, loading proceeds (the check
/// is advisory — callers that require the key should verify separately).
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the JSON file.
/// \param[in]  expected_schema_version  If non-empty, check `$schema` key.
/// \return     Result with code==kOk and field audit on success.
template <typename T>
[[nodiscard]] Result load_from_json_file(T& config, const std::string& path,
                                         std::string_view expected_schema_version = "") {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    // Read file content.
    std::string content;
    if (auto r = detail::read_file_into_string(path, content); !r.ok()) {
        return r;
    }

    auto result = Result::success();

    // ---- Optional-field audit via recursive DOM walk ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, content);

        // ---- Schema version check (uses the same DOM, no extra parse) ----
        if (!expected_schema_version.empty()) {
            auto schema_it = dom.find("$schema");
            if (schema_it != dom.end() && schema_it->second.is_string()) {
                auto file_ver =
                    schema_it->second.template get<iguana::basic_json_value<char>::string_type>();
                if (file_ver != expected_schema_version) {
                    auto msg = std::string("expected schema version '")
                               + std::string(expected_schema_version) + "' but file has '"
                               + file_ver + "'";
                    return Result::failure(ErrorCode::kSchemaMismatch, std::move(msg));
                }
            }
            // $schema absent or non-string → no error (permissive by default)
        }

        // ---- Optional-field audit (must run BEFORE from_json) ----
        // The audit walks the JSON DOM to discover which optional fields are
        // physically present vs. absent in the document — info that from_json
        // discards.  We run the audit on a default-constructed temporary
        // rather than the caller's config: the audit only needs the struct's
        // type information (via for_each over YLT_REFL members) to discover
        // presence/absence.  The struct mutations (nullopt, vector
        // push_backs, etc.) are transient scaffolding to drive the
        // iteration, and running them on a temporary keeps the caller's
        // config untouched if the subsequent from_json fails.
        //     IMPORTANT: from_json must ALWAYS run after the audit, never
        // before.  Any refactor that swaps this ordering would silently
        // corrupt nested-struct and vector fields (these recursion branches
        // zero out freshly-populated data), and the test suite would not
        // catch it (tests only assert the audit lists, not the struct values
        // after loading).
        T audit_temp{};
        detail::audit_json_recursive(audit_temp, dom, result.absent_optionals,
                                     result.present_fields);
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kJsonParseError, e.what());
    }

    // ---- Actual struct population ----
    try {
        iguana::from_json(config, content.begin(), content.end());
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kJsonDeserializeError, e.what());
    }

    return result;
}

/// Load a JSON config file, then run a caller-supplied validator.
///
/// Combines load_from_json_file and validation into a single call.  If loading
/// fails the load error is returned without calling the validator.  If loading
/// succeeds, the validator is invoked on the populated config; a validation
/// failure is returned as kValidationError, otherwise the load result (with
/// audit info) is returned.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \tparam Validator  Callable accepting `const T&` and returning Result
///                    (e.g. generated validate_AppConfig).
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the JSON file.
/// \param[in]  validator  Validation function.
/// \param[in]  expected_schema_version  If non-empty, check `$schema` key.
/// \return     Result with code==kOk, field audit, and validation pass.
template <typename T, typename Validator>
[[nodiscard]] Result load_from_json_file_and_validate(
    T& config, const std::string& path, Validator&& validator,
    std::string_view expected_schema_version = "") {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    auto r = load_from_json_file(config, path, expected_schema_version);
    if (!r.ok()) {
        return r;
    }
    auto vr = std::forward<Validator>(validator)(config);
    if (!vr.ok()) {
        return vr;
    }
    return r;
}

/// Load a JSON string into a struct with optional-field audit.
///
/// When \p expected_schema_version is non-empty, the loader checks for a
/// `"$schema"` key at the top level of the JSON object.  If present and its
/// string value does not match the expected version, the result is
/// kSchemaMismatch.  If `"$schema"` is absent, loading proceeds (the check
/// is advisory — callers that require the key should verify separately).
template <typename T>
[[nodiscard]] Result load_from_json_string(T& config, const std::string& json_str,
                                           std::string_view expected_schema_version = "") {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    auto result = Result::success();

    // ---- Optional-field audit via recursive DOM walk ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, json_str);

        // ---- Schema version check (uses the same DOM, no extra parse) ----
        if (!expected_schema_version.empty()) {
            auto schema_it = dom.find("$schema");
            if (schema_it != dom.end() && schema_it->second.is_string()) {
                auto file_ver =
                    schema_it->second.template get<iguana::basic_json_value<char>::string_type>();
                if (file_ver != expected_schema_version) {
                    auto msg = std::string("expected schema version '")
                               + std::string(expected_schema_version) + "' but file has '"
                               + file_ver + "'";
                    return Result::failure(ErrorCode::kSchemaMismatch, std::move(msg));
                }
            }
            // $schema absent or non-string → no error (permissive by default)
        }

        // ---- Optional-field audit (must run BEFORE from_json) ----
        // See the identical comment in load_from_json_file for the full
        // rationale.  In short: the audit discovers field presence from the
        // DOM using a default-constructed temporary; the struct mutations are
        // transient scaffolding that from_json overwrites.  from_json must
        // ALWAYS run after the audit.
        T audit_temp{};
        detail::audit_json_recursive(audit_temp, dom, result.absent_optionals,
                                     result.present_fields);
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kJsonParseError, e.what());
    }

    // ---- Actual struct population ----
    try {
        iguana::from_json(config, json_str);
    } catch (const std::exception& e) {
        return Result::failure(ErrorCode::kJsonDeserializeError, e.what());
    }

    return result;
}

/// Load a JSON string, then run a caller-supplied validator.
///
/// Combines load_from_json_string and validation into a single call.  If
/// loading fails the load error is returned without calling the validator.
/// If loading succeeds, the validator is invoked on the populated config;
/// a validation failure is returned as kValidationError, otherwise the load
/// result (with audit info) is returned.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \tparam Validator  Callable accepting `const T&` and returning Result
///                    (e.g. generated validate_AppConfig).
/// \param[out] config  Populated config struct.
/// \param[in]  json_str  JSON string to parse.
/// \param[in]  validator  Validation function.
/// \param[in]  expected_schema_version  If non-empty, check `$schema` key.
/// \return     Result with code==kOk, field audit, and validation pass.
template <typename T, typename Validator>
[[nodiscard]] Result load_from_json_string_and_validate(
    T& config, const std::string& json_str, Validator&& validator,
    std::string_view expected_schema_version = "") {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    auto r = load_from_json_string(config, json_str, expected_schema_version);
    if (!r.ok()) {
        return r;
    }
    auto vr = std::forward<Validator>(validator)(config);
    if (!vr.ok()) {
        return vr;
    }
    return r;
}

/// Serialize a config struct to a JSON string.
///
/// Uses iguana::to_json for compact output. When \p pretty is true, the
/// compact JSON is post-processed through iguana::prettify().
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[in] config  The config struct to serialize.
/// \param[in] pretty  If true, produce indented/pretty JSON.
/// \param[out] err_msg  If non-null and serialization throws, filled with the
///             exception's what() message (so callers can surface a real
///             diagnostic instead of a generic "failed to serialize").
/// \return  The JSON string, or std::nullopt if serialization throws.
template <typename T>
std::optional<std::string> to_json(const T& config, bool pretty = false,
                                   std::string* err_msg = nullptr) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    try {
        iguana::string_stream ss;
        iguana::to_json(config, ss);
        std::string result = std::move(ss);
        if (pretty) {
            return iguana::prettify(result);
        }
        return result;
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

/// Write a config struct to a JSON file.
///
/// Serializes the struct and writes it to the given path. The file is
/// truncated if it already exists.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[in] config  The config struct to serialize.
/// \param[in] path    Path to the output JSON file.
/// \param[in] pretty  If true, produce indented/pretty JSON (default: true).
/// \return  Result with code==kOk on success; kJsonSerializeError or
///          kFileWriteError on failure.
template <typename T>
[[nodiscard]] Result save_to_json_file(const T& config, const std::string& path,
                                       bool pretty = true) {
    static_assert(ylt::reflection::is_ylt_refl_v<T>,
                  "T must be annotated with YLT_REFL(...). "
                  "Add YLT_REFL(YourStruct, field1, field2, ...) after the struct definition.");

    std::string serialize_err;
    auto json_opt = to_json(config, pretty, &serialize_err);
    if (!json_opt.has_value()) {
        // Surface the underlying exception message (if any) so a real
        // serialization failure is debuggable instead of a bare string.
        std::string msg = "failed to serialize config to JSON";
        if (!serialize_err.empty()) {
            msg += ": ";
            msg += serialize_err;
        }
        return Result::failure(ErrorCode::kJsonSerializeError, std::move(msg));
    }
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file) {
        return Result::failure(ErrorCode::kFileWriteError, path);
    }
    file << json_opt.value();
    // Detect a failed write *before* close.  operator<< on a buffered
    // ofstream can return having only buffered the bytes; a disk-full or
    // I/O error surfaces when the buffer is flushed.  We force the flush
    // explicitly and inspect the stream state (failbit/badbit) — checking
    // good() *after* close is unreliable, since close() also sets failbit on
    // a failed flush but good() is additionally false when eofbit is set.
    file.flush();
    if (file.fail()) {
        // close() anyway to release the (possibly truncated) file handle.
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
