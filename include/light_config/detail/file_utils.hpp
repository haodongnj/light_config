#pragma once

#include <string>

#include "light_config/result.hpp"
#include <fstream>

namespace light_config {
namespace detail {

inline Result read_file_into_string(const std::string& path, std::string& content) {
    // Open at-end so tellg() gives the size on the same fd — avoids TOCTOU
    // between a separate file_size() call and the read.
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    if (!file) {
        return Result::failure(ErrorCode::kFileReadError, path);
    }
    auto size = file.tellg();
    if (size == std::streampos(-1)) {
        return Result::failure(ErrorCode::kFileReadError, path);
    }
    if (size == 0) {
        return Result::failure(ErrorCode::kFileEmpty, path);
    }
    try {
        content.resize(static_cast<std::size_t>(size));
    } catch (const std::bad_alloc&) {
        return Result::failure(ErrorCode::kFileReadError, "allocation failure");
    }
    file.seekg(0);
    file.read(content.data(), size);
    content.resize(file.gcount());
    return Result::success();
}

}  // namespace detail
}  // namespace light_config
