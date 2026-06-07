#pragma once

#include <exception>
#include <fstream>
#include <system_error>

#include <ylt/struct_json/json_reader.h>

#include "light_config/load_result.hpp"

namespace light_config {

/// Load a JSON config file into a struct and report optional-field presence.
///
/// The JSON is parsed twice: once into a DOM to audit optional keys, and
/// once to populate the struct. This gives accurate absent-vs-null
/// detection for std::optional fields.
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

    // ---- Optional-field audit via DOM parse ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, content);

        ylt::reflection::for_each(config,
            [&](auto& member, std::string_view name, auto /*index*/) {
                std::string key(name);
                auto it = dom.find(key);
                if (it == dom.end()) {
                    using field_t =
                        std::decay_t<decltype(member)>;
                    if constexpr (detail::is_optional_v<field_t>) {
                        result.absent_optionals.emplace_back(name);
                        member = std::nullopt;
                    }
                } else {
                    result.present_fields.emplace_back(name);
                }
            });
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

    // ---- Optional-field audit via DOM parse ----
    try {
        iguana::jobject dom;
        iguana::parse(dom, json_str);

        ylt::reflection::for_each(config,
            [&](auto& member, std::string_view name, auto /*index*/) {
                std::string key(name);
                auto it = dom.find(key);
                if (it == dom.end()) {
                    using field_t =
                        std::decay_t<decltype(member)>;
                    if constexpr (detail::is_optional_v<field_t>) {
                        result.absent_optionals.emplace_back(name);
                        member = std::nullopt;
                    }
                } else {
                    result.present_fields.emplace_back(name);
                }
            });
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
