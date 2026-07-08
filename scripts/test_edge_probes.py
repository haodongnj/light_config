#!/usr/bin/env python3
"""Temporary stub — full harness in Task 4. Verifies helper imports."""
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import _gen_test_helpers as h  # noqa: E402


def main() -> int:
    # The renamed helpers must be importable.
    assert hasattr(h, "check"), "missing check"
    assert hasattr(h, "COMPILER"), "missing COMPILER"
    assert hasattr(h, "compile_dir"), "missing compile_dir"
    assert hasattr(h, "generate_to_dir"), "missing generate_to_dir"
    assert hasattr(h, "generate_exits"), "missing generate_exits"
    print("helper imports OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
