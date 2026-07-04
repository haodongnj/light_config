#pragma once

#include <ylt/reflection/user_reflect_macro.hpp>

#include <string>
#include <vector>

#include "light_config/load_result.hpp"

namespace light_config {
namespace detail {

/// Recursively audit optional fields in a struct after YAML loading.
/// Uses ylt::reflection::for_each and recurses into members that have
/// YLT_REFL. prefix is the dot-joined parent path.
template <typename T>
void audit_yaml_recursive(const T &obj,
                          std::vector<std::string> &absent_optionals,
                          std::vector<std::string> &present_fields,
                          const std::string &prefix = "") {
  ylt::reflection::for_each(obj, [&](auto &member, std::string_view name,
                                     auto /*index*/) {
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

} // namespace detail
} // namespace light_config
