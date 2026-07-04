#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_json/json_reader.h>
#include <ylt/struct_json/json_writer.h>

#include <exception>

#include "light_config/detail/audit_json.hpp"
#include "light_config/detail/file_utils.hpp"
#include "light_config/load_result.hpp"
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
/// \return     LoadResult with code==kOk and field audit on success.
template <typename T>
LoadResult load_from_json_file(T &config, const std::string &path,
                               std::string_view expected_schema_version = "") {
  // Read file content.
  std::string content;
  if (auto r = detail::read_file_into_string(path, content); !r.ok()) {
    return r;
  }

  auto result = LoadResult::success();

  // ---- Optional-field audit via recursive DOM walk ----
  try {
    iguana::jobject dom;
    iguana::parse(dom, content);

    // ---- Schema version check (uses the same DOM, no extra parse) ----
    if (!expected_schema_version.empty()) {
      auto schema_it = dom.find("$schema");
      if (schema_it != dom.end() && schema_it->second.is_string()) {
        auto file_ver =
            schema_it->second
                .template get<iguana::basic_json_value<char>::string_type>();
        if (file_ver != expected_schema_version) {
          auto msg = std::string("expected schema version '") +
                     std::string(expected_schema_version) + "' but file has '" +
                     file_ver + "'";
          return LoadResult::failure(ErrorCode::kSchemaMismatch,
                                     std::move(msg));
        }
      }
      // $schema absent or non-string → no error (permissive by default)
    }

    detail::audit_json_recursive(config, dom, result.absent_optionals,
                                 result.present_fields);
  } catch (const std::exception &e) {
    return LoadResult::failure(ErrorCode::kJsonParseError, e.what());
  }

  // ---- Actual struct population ----
  try {
    iguana::from_json(config, content.begin(), content.end());
  } catch (const std::exception &e) {
    return LoadResult::failure(ErrorCode::kJsonDeserializeError, e.what());
  }

  return result;
}

/// Load a JSON string into a struct with optional-field audit.
///
/// When \p expected_schema_version is non-empty, the loader checks for a
/// `"$schema"` key at the top level of the JSON object.  If present and its
/// string value does not match the expected version, the result is
/// kSchemaMismatch.  If `"$schema"` is absent, loading proceeds (the check
/// is advisory — callers that require the key should verify separately).
template <typename T>
LoadResult
load_from_json_string(T &config, const std::string &json_str,
                      std::string_view expected_schema_version = "") {
  auto result = LoadResult::success();

  // ---- Optional-field audit via recursive DOM walk ----
  try {
    iguana::jobject dom;
    iguana::parse(dom, json_str);

    // ---- Schema version check (uses the same DOM, no extra parse) ----
    if (!expected_schema_version.empty()) {
      auto schema_it = dom.find("$schema");
      if (schema_it != dom.end() && schema_it->second.is_string()) {
        auto file_ver =
            schema_it->second
                .template get<iguana::basic_json_value<char>::string_type>();
        if (file_ver != expected_schema_version) {
          auto msg = std::string("expected schema version '") +
                     std::string(expected_schema_version) + "' but file has '" +
                     file_ver + "'";
          return LoadResult::failure(ErrorCode::kSchemaMismatch,
                                     std::move(msg));
        }
      }
      // $schema absent or non-string → no error (permissive by default)
    }

    detail::audit_json_recursive(config, dom, result.absent_optionals,
                                 result.present_fields);
  } catch (const std::exception &e) {
    return LoadResult::failure(ErrorCode::kJsonParseError, e.what());
  }

  // ---- Actual struct population ----
  try {
    iguana::from_json(config, json_str);
  } catch (const std::exception &e) {
    return LoadResult::failure(ErrorCode::kJsonDeserializeError, e.what());
  }

  return result;
}

/// Serialize a config struct to a JSON string.
///
/// Uses iguana::to_json for compact output. When \p pretty is true, the
/// compact JSON is post-processed through iguana::prettify().
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[in] config  The config struct to serialize.
/// \param[in] pretty  If true, produce indented/pretty JSON.
/// \return  The JSON string, or std::nullopt if serialization throws.
template <typename T>
std::optional<std::string> to_json(const T &config, bool pretty = false) {
  try {
    iguana::string_stream ss;
    iguana::to_json(config, ss);
    std::string result = std::move(ss);
    if (pretty) {
      return iguana::prettify(result);
    }
    return result;
  } catch (const std::exception &) {
    // Defensive: iguana serialization does not throw for well-formed
    // YLT_REFL-annotated structs. This catch exists to uphold the API
    // contract (never throw from a load/save function) against
    // hypothetical edge cases (bad_alloc, corrupted internal state).
    // This path is intentionally uncovered by tests.
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
/// \return  LoadResult with code==kOk on success; kJsonSerializeError or
///          kFileWriteError on failure.
template <typename T>
LoadResult save_to_json_file(const T &config, const std::string &path,
                             bool pretty = true) {
  auto json_opt = to_json(config, pretty);
  if (!json_opt.has_value()) {
    return LoadResult::failure(ErrorCode::kJsonSerializeError,
                               "failed to serialize config to JSON");
  }
  std::ofstream file(path, std::ios::binary | std::ios::trunc);
  if (!file) {
    return LoadResult::failure(ErrorCode::kFileWriteError, path);
  }
  file << json_opt.value();
  file.close();
  if (!file.good()) {
    return LoadResult::failure(ErrorCode::kFileWriteError, path);
  }
  return LoadResult::success();
}

} // namespace light_config
