#pragma once

#include <exception>
#include <fstream>
#include <system_error>

#include <ylt/struct_json/json_reader.h>
#include <ylt/reflection/user_reflect_macro.hpp>

#include "light_config/load_result.hpp"

namespace light_config {
namespace detail {

/// Recursively audit optional fields against a JSON DOM sub-object.
/// prefix is the dot-joined parent path (e.g., "server" or "server.nested").
template <typename T>
void audit_json_recursive(T& obj, const iguana::jobject& dom,
                          std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          const std::string& prefix = "") {
    ylt::reflection::for_each(obj,
        [&](auto& member, std::string_view name, auto /*index*/) {
            std::string key(name);
            std::string full_name = prefix.empty()
                ? std::string(name)
                : prefix + "." + std::string(name);
            auto it = dom.find(key);

            using field_t = std::decay_t<decltype(member)>;

            if (it == dom.end()) {
                if constexpr (is_optional_v<field_t>) {
                    absent_optionals.push_back(full_name);
                    member = std::nullopt;
                }
            } else {
                present_fields.push_back(full_name);

                // Recurse into nested struct members with YLT_REFL
                if constexpr (ylt::reflection::is_ylt_refl_v<field_t>) {
                    if (it->second.is_object()) {
                        const auto& sub_dom = it->second.template get<
                            iguana::basic_json_value<char>::object_type>();
                        audit_json_recursive(member, sub_dom,
                                            absent_optionals, present_fields,
                                            full_name);
                    }
                }
            }
        });
}

} // namespace detail

/// Load a JSON config file into a struct and report optional-field presence.
///
/// The JSON is parsed once into a DOM to audit optional keys, and
/// once to populate the struct. Nested structs (with YLT_REFL) are
/// recursively audited, with dot-separated field paths in the result.
///
/// \tparam T  A struct annotated with YLT_REFL.
/// \param[out] config  Populated config struct.
/// \param[in]  path    Path to the JSON file.
/// \return     LoadResult with code==kOk and field audit on success.
template <typename T>
LoadResult load_from_json_file(T& config, const std::string& path) {
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

    auto result = LoadResult::success();

    // ---- Optional-field audit via recursive DOM walk ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, content);
        detail::audit_json_recursive(config, dom,
                                     result.absent_optionals,
                                     result.present_fields);
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kJsonParseError, e.what());
    }

    // ---- Actual struct population ----
    try {
        iguana::from_json(config, content.begin(), content.end());
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kJsonDeserializeError, e.what());
    }

    return result;
}

/// Load a JSON string into a struct with optional-field audit.
template <typename T>
LoadResult load_from_json_string(T& config, const std::string& json_str) {
    auto result = LoadResult::success();

    // ---- Optional-field audit via recursive DOM walk ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, json_str);
        detail::audit_json_recursive(config, dom,
                                     result.absent_optionals,
                                     result.present_fields);
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kJsonParseError, e.what());
    }

    // ---- Actual struct population ----
    try {
        iguana::from_json(config, json_str);
    } catch (const std::runtime_error& e) {
        return LoadResult::failure(ErrorCode::kJsonDeserializeError, e.what());
    }

    return result;
}

}  // namespace light_config
