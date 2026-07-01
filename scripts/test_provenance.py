#!/usr/bin/env python3
"""Self-test for the Provenance stamp block."""
import sys
sys.path.insert(0, "scripts")
from gen_config import Provenance, _provenance_block  # noqa: E402

prov = Provenance(
    schema_version="1.3.0",
    source_csv="sample_config.csv",
    csv_md5="a1b2c3d4e5f67890a1b2c3d4e5f67890",
    generated_at="2026-06-28T14:32:05+00:00",
    generator="light_config / scripts/gen_config.py",
)
block = _provenance_block(prov)
assert "--- Schema provenance ---" in block, block
assert "schema_version : 1.3.0" in block, block
assert "source_csv     : sample_config.csv" in block, block
assert "csv_md5        : a1b2c3d4e5f67890a1b2c3d4e5f67890" in block, block
assert "generated_at   : 2026-06-28T14:32:05+00:00" in block, block
assert "generator      : light_config / scripts/gen_config.py" in block, block
for line in block.splitlines():
    assert line.startswith("///") or line == "", line
print("OK provenance block")
