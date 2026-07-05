"""
Configuration dataclass for the CSV-driven C++ code generator.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GeneratorConfig:
    """All tunables for a generation run."""

    input_csv: str
    output_dir: str = "examples/"
    hpp_dir: Optional[str] = None
    src_dir: Optional[str] = None
    struct_name: str = ""
    namespace: str = ""
    per_struct: bool = False
    generate_samples: bool = False
    samples_only: bool = False
    schema_version_override: Optional[str] = None

    # -- derived helpers ---------------------------------------------------

    @property
    def effective_hpp_dir(self) -> Path:
        return Path(self.hpp_dir) if self.hpp_dir else Path(self.output_dir)

    @property
    def effective_src_dir(self) -> Path:
        return Path(self.src_dir) if self.src_dir else Path(self.output_dir)

    @property
    def effective_samples_dir(self) -> Path:
        return Path(self.output_dir)
