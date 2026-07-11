#!/usr/bin/env python3
"""Shared primitives for the generator self-tests.

Factored out of test_cpp_compile.py so test_edge_probes.py can reuse the
compile/reject harness without duplicating ~60 lines.  No pytest — just
stdlib + the sibling gen_config module.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gen_config  # noqa: E402
from _gen_config.exceptions import GeneratorError  # noqa: E402

# Shared pass/fail counter.  Each test file's main() reads get_fail_count()
# to decide its exit code.
_FAIL = 0


def check(cond: bool, msg: str) -> None:
    global _FAIL
    if not cond:
        print(f"[FAIL] {msg}")
        _FAIL += 1
    else:
        print(f"[PASS] {msg}")


def get_fail_count() -> int:
    return _FAIL


def _find_compiler() -> str:
    for c in ("c++", "clang++", "g++"):
        if shutil.which(c):
            return c
    return ""


COMPILER = _find_compiler()
_YLT = (SCRIPT_DIR.parent / "third_party" / "yalantinglibs" / "include").resolve()
# yalantinglibs ships three include roots (mirrors the SYSTEM INTERFACE paths
# configured in the root CMakeLists.txt).
YLT_INCLUDE_DIRS = [
    str(_YLT),
    str((_YLT / "ylt" / "standalone").resolve()),
    str((_YLT / "ylt" / "thirdparty").resolve()),
]
LIGHT_CONFIG_INCLUDE = str((SCRIPT_DIR.parent / "include").resolve())


def compile_dir(out_dir: Path, extra_hpp_check: str = "") -> tuple[bool, str]:
    """Compile every *.hpp/*.cpp pair in *out_dir* with -fsyntax-only.

    Returns (ok, combined_diagnostics).  Mirrors the CMake build's intent:
    catch real codegen defects under -Werror without tripping on
    yalantinglibs reflection-macro noise (suppressed via -isystem).
    """
    if not COMPILER:
        return False, "no C++ compiler (c++/clang++/g++) on PATH"
    cpps = sorted(out_dir.glob("*.cpp"))
    if not cpps:
        return False, "no .cpp files generated"
    diag: list[str] = []
    ok = True
    for cpp in cpps:
        cmd = [
            COMPILER, "-std=c++17", "-fsyntax-only",
            "-Wall", "-Werror",
            "-Wno-unused-parameter",   # YLT_REFL macro expansion
            f"-I{out_dir}",
            f"-I{LIGHT_CONFIG_INCLUDE}",
        ] + [f"-isystem{p}" for p in YLT_INCLUDE_DIRS] + [str(cpp)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            ok = False
            diag.append(f"--- {cpp.name} ---\n{proc.stderr}")
    return ok, "\n".join(diag)


def generate_to_dir(csv_text: str, *, namespace: str = "",
                    generate_samples: bool = False) -> Path:
    """Generate from *csv_text* into a fresh temp dir; return the out dir path.

    If *namespace* is non-empty it is set on the GeneratorConfig (belt-and-
    suspenders — most probe CSVs also declare namespace in __metadata__).
    """
    tmp = Path(tempfile.mkdtemp(prefix="lc_compile_test_"))
    csv_path = tmp / "schema.csv"
    csv_path.write_text(csv_text)
    out_dir = tmp / "out"
    out_dir.mkdir()
    cfg = gen_config.GeneratorConfig(
        input_csv=str(csv_path),
        output_dir=str(out_dir),
        generate_samples=generate_samples,
    )
    if namespace:
        cfg.namespace = namespace
    with open(os.devnull, "w") as devnull:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = devnull
        try:
            gen_config.generate(cfg)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
    return out_dir


def generate_exits(csv_text: str) -> bool:
    """Return True if generating from *csv_text* raises GeneratorError / exits."""
    tmp = Path(tempfile.mkdtemp(prefix="lc_gen_reject_"))
    csv_path = tmp / "schema.csv"
    csv_path.write_text(csv_text)
    out_dir = tmp / "out"
    out_dir.mkdir()
    cfg = gen_config.GeneratorConfig(input_csv=str(csv_path), output_dir=str(out_dir))
    old_err = sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stderr = devnull
            gen_config.generate(cfg)
        return False
    except (SystemExit, GeneratorError):
        return True
    finally:
        sys.stderr = old_err
