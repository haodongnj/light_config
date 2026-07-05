#pragma once

#include <filesystem>
#include <string>
#include <system_error>

#include "light_config/result.hpp"
#include <fstream>

namespace light_config {
namespace detail {

inline Result read_file_into_string(const std::string& path, std::string& content) {
    std::error_code ec;
    auto size = std::filesystem::file_size(path, ec);
    if (ec) {
        return Result::failure(ErrorCode::kFileReadError, ec.message());
    }
    if (size == 0) {
        return Result::failure(ErrorCode::kFileEmpty, path);
    }
    try {
        content.resize(size);
    } catch (const std::bad_alloc&) {
        return Result::failure(ErrorCode::kFileReadError, "allocation failure");
    }
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        return Result::failure(ErrorCode::kFileReadError, path);
    }
    file.read(content.data(), size);
    content.resize(file.gcount());
    return Result::success();
}

}  // namespace detail
}  // namespace light_config
