#pragma once

#include <filesystem>
#include <string>
#include <system_error>

#include "light_config/load_result.hpp"
#include <fstream>

namespace light_config {
namespace detail {

inline LoadResult read_file_into_string(const std::string& path, std::string& content) {
    std::error_code ec;
    auto size = std::filesystem::file_size(path, ec);
    if (ec) {
        return LoadResult::failure(ErrorCode::kFileReadError, ec.message());
    }
    if (size == 0) {
        return LoadResult::failure(ErrorCode::kFileEmpty, path);
    }
    try {
        content.resize(size);
    } catch (const std::bad_alloc&) {
        return LoadResult::failure(ErrorCode::kFileReadError, "allocation failure");
    }
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        return LoadResult::failure(ErrorCode::kFileReadError, path);
    }
    file.read(content.data(), size);
    content.resize(file.gcount());
    return LoadResult::success();
}

}  // namespace detail
}  // namespace light_config
