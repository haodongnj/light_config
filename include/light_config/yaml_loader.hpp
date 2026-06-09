#pragma once

#include <cstdint>
#include <exception>
#include <fstream>
#include <system_error>

#include <ylt/struct_yaml/yaml_reader.h>
#include <ylt/reflection/user_reflect_macro.hpp>

#include "light_config/load_result.hpp"

namespace light_config {
namespace detail {

/// Recursively audit optional fields in a struct after YAML loading.
/// Uses ylt::reflection::for_each and recurses into members that have
/// YLT_REFL. prefix is the dot-joined parent path.
template <typename T>
void audit_yaml_recursive(const T& obj,
                          std::vector<std::string>& absent_optionals,
                          std::vector<std::string>& present_fields,
                          const std::string& prefix = "") {
    ylt::reflection::for_each(obj,
        [&](auto& member, std::string_view name, auto /*index*/) {
            std::string full_name = prefix.empty()
                ? std::string(name)
                : prefix + "." + std::string(name);

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
                audit_yaml_recursive(member, absent_optionals, present_fields,
                                    full_name);
            }
        });
}

} // namespace detail

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
    detail::audit_yaml_recursive(config, result.absent_optionals,
                                 result.present_fields);

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

    detail::audit_yaml_recursive(config, result.absent_optionals,
                                 result.present_fields);

    return result;
}

}  // namespace light_config
