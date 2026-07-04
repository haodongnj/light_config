#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_json/json_reader.h>

#include <string>
#include <vector>

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
    ylt::reflection::for_each(obj, [&](auto& member, std::string_view name, auto /*index*/) {
        std::string key(name);
        std::string full_name =
            prefix.empty() ? std::string(name) : prefix + "." + std::string(name);
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
                    const auto& sub_dom =
                        it->second.template get<iguana::basic_json_value<char>::object_type>();
                    audit_json_recursive(member, sub_dom, absent_optionals, present_fields,
                                         full_name);
                }
            }
        }
    });
}

}  // namespace detail
}  // namespace light_config
