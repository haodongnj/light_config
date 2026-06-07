#pragma once

#include <cstdint>
#include <exception>
#include <fstream>
#include <system_error>

#include <ylt/struct_yaml/yaml_reader.h>

#include "light_config/load_result.hpp"

namespace light_config {

/// Load a YAML config file into a struct and report optional-field presence.
///
/// YAML limitation: iguana has no YAML DOM API, so absent-vs-null detection
/// is not possible. All std::optional fields that end up std::nullopt after
/// loading are reported as absent (which includes fields explicitly set to
/// null in the YAML).
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

    // Audit optional fields post-load. We cannot distinguish absent from
    // explicit null with the iguana YAML API.
    ylt::reflection::for_each(config,
        [&](auto& member, std::string_view name, auto /*index*/) {
            using field_t = std::decay_t<decltype(member)>;
            if constexpr (detail::is_optional_v<field_t>) {
                if (member.has_value()) {
                    result.present_fields.emplace_back(name);
                } else {
                    result.absent_optionals.emplace_back(name);
                }
            } else {
                result.present_fields.emplace_back(name);
            }
        });

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

    ylt::reflection::for_each(config,
        [&](auto& member, std::string_view name, auto /*index*/) {
            using field_t = std::decay_t<decltype(member)>;
            if constexpr (detail::is_optional_v<field_t>) {
                if (member.has_value()) {
                    result.present_fields.emplace_back(name);
                } else {
                    result.absent_optionals.emplace_back(name);
                }
            } else {
                result.present_fields.emplace_back(name);
            }
        });

    return result;
}

}  // namespace light_config
