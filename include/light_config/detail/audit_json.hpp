#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>
#include <ylt/struct_json/json_reader.h>

#include <string>
#include <vector>

#include "light_config/result.hpp"

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
            // (H6a) Recurse into a present std::optional<T> when T is a
            // YLT_REFL struct and the DOM value is an object (not null).
            else if constexpr (is_optional_v<field_t>) {
                using inner_t = typename field_t::value_type;
                if constexpr (ylt::reflection::is_ylt_refl_v<inner_t>) {
                    if (it->second.is_object()) {
                        member = inner_t{};
                        const auto& sub_dom =
                            it->second.template get<iguana::basic_json_value<char>::object_type>();
                        audit_json_recursive(*member, sub_dom, absent_optionals, present_fields,
                                             full_name);
                    }
                }
                // (H6a extended) Recurse into a present
                // std::optional<std::vector<T>> of YLT_REFL structs.
                // Report element subfields with an index-agnostic "[]"
                // path segment (audit reports presence, not positions).
                else if constexpr (is_range_v<inner_t>) {
                    using elem_t = typename inner_t::value_type;
                    if constexpr (ylt::reflection::is_ylt_refl_v<elem_t>) {
                        if (it->second.is_array()) {
                            member = inner_t{};
                            const auto& arr =
                                it->second
                                    .template get<iguana::basic_json_value<char>::array_type>();
                            for (const auto& el : arr) {
                                if (el.is_object()) {
                                    elem_t e{};
                                    const auto& sub_dom = el.template get<
                                        iguana::basic_json_value<char>::object_type>();
                                    audit_json_recursive(e, sub_dom, absent_optionals,
                                                         present_fields, full_name + "[]");
                                    member->push_back(std::move(e));
                                }
                            }
                        }
                    }
                }
            }
            // (H6b) Recurse into a std::vector<T> (or array) of YLT_REFL
            // structs.  Report element subfields with an index-agnostic
            // "[]" path segment (audit reports presence, not positions).
            else if constexpr (is_range_v<field_t>) {
                using elem_t = typename field_t::value_type;
                if constexpr (ylt::reflection::is_ylt_refl_v<elem_t>) {
                    if (it->second.is_array()) {
                        const auto& arr =
                            it->second.template get<iguana::basic_json_value<char>::array_type>();
                        member.clear();
                        for (const auto& el : arr) {
                            if (el.is_object()) {
                                elem_t e{};
                                const auto& sub_dom =
                                    el.template get<iguana::basic_json_value<char>::object_type>();
                                audit_json_recursive(e, sub_dom, absent_optionals, present_fields,
                                                     full_name + "[]");
                                member.push_back(std::move(e));
                            }
                        }
                    }
                }
            }
        }
    });
}

}  // namespace detail
}  // namespace light_config
