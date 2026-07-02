# Environment Setup Guide (Ubuntu 22.04)

This guide helps new contributors get a working build environment on **Ubuntu 22.04 LTS** (Jammy).

## Prerequisites

```bash
sudo apt update
sudo apt install -y build-essential cmake git clang-format python3
```

| Package | Purpose |
|---------|---------|
| `build-essential` | GCC 11+, make, libc dev headers |
| `cmake` | Build system (≥ 3.16 required; Jammy ships 3.22) |
| `git` | Version control |
| `clang-format` | C++ code formatter |
| `python3` | CSV code generator (`scripts/gen_config.py`) |

## Check Your Toolchain

```bash
g++ --version       # expect 11.x or newer
cmake --version     # expect 3.22+
clang-format --version  # expect 14.x on Jammy
python3 --version   # expect 3.10+
```

## Clone and Build

```bash
git clone <repo-url> light_config
cd light_config
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug
cmake --build build
```

If the build succeeds, you should see targets like `test_basic` and `example_json` compiled.

## Run Tests

```bash
cmake --build build --target test_basic
./build/tests/test_basic
```

Or with CTest:

```bash
cd build && ctest --output-on-failure
```

## Code Formatting

### One-time format

```bash
# Format all hand-written sources
cmake --build build --target format

# Or format a single file
clang-format -i --style=file include/light_config/light_config.hpp
```

### Check compliance (CI-style)

```bash
cmake --build build --target check-format
```

This runs `clang-format` in dry-run mode and fails if any file needs formatting.

### Pre-commit hook (auto-format on every commit)

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

After this, every `git commit` will automatically format your staged C++ files. The hook:
- Only touches staged files matching `*.hpp`, `*.cpp`, `*.h`, `*.c`, `*.cc`, `*.cxx`.
- Formats the staged content without disturbing unstaged changes.
- Prints a warning but allows the commit if `clang-format` is missing.

### VS Code (optional)

Install the **clangd** extension (`llvm-vs-code-extensions.vscode-clangd`) and add to `.vscode/settings.json`:

```json
{
  "[cpp]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "llvm-vs-code-extensions.vscode-clangd"
  },
  "[c]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "llvm-vs-code-extensions.vscode-clangd"
  }
}
```

## Static Analysis (optional)

```bash
sudo apt install -y clang-tidy
cmake -B build -S . -DCMAKE_BUILD_TYPE=Debug -DENABLE_CLANG_TIDY=ON
cmake --build build
```

Clang-tidy checks run inline with compilation — violations appear as warnings.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `cmake: command not found` | `sudo apt install cmake` |
| CMake complains about C++17 | `sudo apt install g++-11` and set `CC=gcc-11 CXX=g++-11` |
| `fatal error: ylt/...` | Make sure `third_party/yalantinglibs` exists (it's vendored in the repo) |
| `clang-format: command not found` | `sudo apt install clang-format` |
| pre-commit hook not running | `ls -la .git/hooks/pre-commit` — should be a symlink to `scripts/pre-commit` |
