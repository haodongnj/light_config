"""
Code generator — orchestrates C++ code generation from a SchemaModel + config.
"""

from collections import OrderedDict
from pathlib import Path

from .config import GeneratorConfig
from .cpp_gen import (
    _make_header_preamble,
    _make_schema_version_constant,
    _make_source_preamble,
    _make_struct_body,
    _make_validate_decl,
    _make_validate_impl,
)
from .provenance import Provenance
from .samples import _build_sample_dict, _write_json, _write_yaml
from .schema import SchemaModel
from .types import (
    _derive_filenames,
    _hpp_to_cpp_name,
    _struct_to_cpp_name,
    _struct_to_hpp_name,
    _to_snake_case,
)


class CodeGenerator:
    """Orchestrates C++ code generation from a schema model + config."""

    def __init__(self, model: SchemaModel, config: GeneratorConfig,
                 provenance: Provenance) -> None:
        self.model = model
        self.config = config
        self.provenance = provenance
        self._struct_name = config.struct_name or model.root
        # Root filenames (used in monolithic mode only)
        self._root_hpp_name, self._root_cpp_name = _derive_filenames(
            config, self._struct_name
        )
        self._include_header = config.include_header or self._root_hpp_name
        # Resolve namespace: CLI flag > __metadata__ > empty (back-compat)
        self._namespace = (
            config.namespace
            or model.metadata.get("namespace", "")
        )

    # -- namespace helpers --------------------------------------------------

    def _ns_open(self) -> list[str]:
        """Opening lines wrapping generated content in the resolved namespace."""
        if not self._namespace:
            return []
        return ["", f"namespace {self._namespace} {{"]

    def _ns_close(self) -> list[str]:
        """Closing line(s) for the resolved namespace block."""
        if not self._namespace:
            return []
        return [f"}} // namespace {self._namespace}"]

    # -- public API --------------------------------------------------------

    def generate_all(self) -> None:
        """Generate all output files in one shot."""
        if self.model.has_explicit_hpp_file:
            self._generate_csv_driven()
        elif self.config.per_struct:
            self._generate_per_struct()
        else:
            self.generate_header()
            self.generate_source()
        if self.config.generate_samples:
            self.generate_samples()
        n_fields = sum(len(v) for v in self.model.group_regular.values())
        print(
            f"  (root: {self.model.root}, "
            f"{len(self.model.ordered_groups)} struct(s), {n_fields} fields)"
        )

    def generate_header(self) -> Path:
        """Generate the single monolithic header file."""
        outdir = self.config.effective_hpp_dir
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / self._root_hpp_name
        content = self._build_monolithic_header_content()
        path.write_text(content)
        print(f"Generated {path}")
        return path

    def generate_source(self) -> Path:
        """Generate the single monolithic source file."""
        outdir = self.config.effective_src_dir
        outdir.mkdir(parents=True, exist_ok=True)
        path = outdir / self._root_cpp_name
        content = self._build_monolithic_source_content()
        path.write_text(content)
        print(f"Generated {path}")
        return path

    def generate_samples(self) -> list[Path]:
        outdir = self.config.effective_samples_dir
        outdir.mkdir(parents=True, exist_ok=True)
        valid_data = _build_sample_dict(
            self.model.group_regular,
            self.model.group_nested,
            self.model.root,
            use_default=True,
            violate=False,
        )
        vj = outdir / "valid_config.json"
        vy = outdir / "valid_config.yaml"
        _write_json(valid_data, vj)
        _write_yaml(valid_data, vy)
        print(f"Generated {vj}")
        print(f"Generated {vy}")
        return [vj, vy]

    # -- file group helpers -----------------------------------------------

    def _build_file_groups(self) -> OrderedDict[str, list[str]]:
        """Return {hpp_name: [group_names]} preserving topological order."""
        result: OrderedDict[str, list[str]] = OrderedDict()
        for gname in self.model.ordered_groups:
            hpp_name = self.model.hpp_file_for(gname)
            result.setdefault(hpp_name, []).append(gname)
        return result

    def _cross_file_includes(self, hpp_name: str, groups: list[str]) -> list[str]:
        """Headers from *other* files that groups in this file depend on."""
        includes: set[str] = set()
        for gname in groups:
            for _, nested_type, _ in self.model.group_nested.get(gname, []):
                nested_hpp = self.model.hpp_file_for(nested_type)
                if nested_hpp != hpp_name:
                    includes.add(nested_hpp)
        return sorted(includes)

    # -- CSV-driven generation --------------------------------------------

    def _generate_csv_driven(self) -> None:
        """Generate .hpp/.cpp pairs according to the CSV hpp_file column."""
        hpp_dir = self.config.effective_hpp_dir
        src_dir = self.config.effective_src_dir
        hpp_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)

        file_groups = self._build_file_groups()

        for hpp_name, groups in file_groups.items():
            hpp_content = self._build_file_group_header(hpp_name, groups)
            hpp_path = hpp_dir / hpp_name
            hpp_path.write_text(hpp_content)
            print(f"Generated {hpp_path}")

            cpp_name = _hpp_to_cpp_name(hpp_name)
            cpp_content = self._build_file_group_source(hpp_name, groups)
            cpp_path = src_dir / cpp_name
            cpp_path.write_text(cpp_content)
            print(f"Generated {cpp_path}")

    def _build_file_group_header(self, hpp_name: str,
                                 groups: list[str]) -> str:
        """Build the .hpp content for a file group containing one or more structs."""
        extra_includes = self._cross_file_includes(hpp_name, groups)
        has_opt = any(
            self.model.group_has_optional(g) for g in groups
        )

        lines: list[str] = [_make_header_preamble(has_opt, extra_includes,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            body, _ = _make_struct_body(
                struct_name,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(body)
            lines.append("")
        schema_ver = self.provenance.schema_version
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            lines.append(_make_schema_version_constant(struct_name, schema_ver))
            lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            lines.append(_make_validate_decl(struct_name))
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_file_group_source(self, hpp_name: str,
                                 groups: list[str]) -> str:
        """Build the .cpp content for a file group."""
        lines: list[str] = [_make_source_preamble(hpp_name, self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in groups:
            struct_name = (
                self._struct_name if gname == self.model.root else gname
            )
            impl = _make_validate_impl(
                struct_name,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(impl)
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    # -- per-struct generation --------------------------------------------

    def _generate_per_struct(self) -> None:
        """Generate one .hpp/.cpp pair per struct group."""
        hpp_dir = self.config.effective_hpp_dir
        src_dir = self.config.effective_src_dir
        hpp_dir.mkdir(parents=True, exist_ok=True)
        src_dir.mkdir(parents=True, exist_ok=True)

        for gname in self.model.ordered_groups:
            is_root = (gname == self.model.root)
            if is_root and self.config.hpp_name:
                hpp_name = self.config.hpp_name
                cpp_name = _hpp_to_cpp_name(hpp_name)
            elif is_root and self.config.struct_name:
                snake = _to_snake_case(self.config.struct_name)
                hpp_name = f"{snake}.hpp"
                cpp_name = f"{snake}.cpp"
            else:
                hpp_name = _struct_to_hpp_name(gname)
                cpp_name = _struct_to_cpp_name(gname)

            hpp_content = self._build_struct_header_content(gname)
            hpp_path = hpp_dir / hpp_name
            hpp_path.write_text(hpp_content)
            print(f"Generated {hpp_path}")

            cpp_content = self._build_struct_source_content(gname, hpp_name)
            cpp_path = src_dir / cpp_name
            cpp_path.write_text(cpp_content)
            print(f"Generated {cpp_path}")

    # -- monolithic content builders --------------------------------------

    def _build_monolithic_header_content(self) -> str:
        lines: list[str] = [
            _make_header_preamble(self.model.has_optional,
                                  provenance=self.provenance)
        ]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in self.model.ordered_groups:
            body, _ = _make_struct_body(
                gname,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(body)
            lines.append("")
        schema_ver = self.provenance.schema_version
        for gname in self.model.ordered_groups:
            lines.append(_make_schema_version_constant(gname, schema_ver))
            lines.append("")
        for gname in self.model.ordered_groups:
            lines.append(_make_validate_decl(gname))
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_monolithic_source_content(self) -> str:
        lines: list[str] = [_make_source_preamble(self._include_header,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        for gname in self.model.ordered_groups:
            impl = _make_validate_impl(
                gname,
                self.model.group_regular[gname],
                self.model.group_nested[gname],
            )
            lines.append(impl)
            lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    # -- per-struct content builders --------------------------------------

    def _build_struct_header_content(self, gname: str) -> str:
        """Build the .hpp content for a single struct group."""
        struct_name = self._struct_name if gname == self.model.root else gname
        nested_types = [
            nt for _, nt, _ in self.model.group_nested.get(gname, [])
        ]
        extra_includes = [_struct_to_hpp_name(nt) for nt in nested_types]
        has_opt = self.model.group_has_optional(gname)

        lines: list[str] = [_make_header_preamble(has_opt, extra_includes,
                                                  self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        body, _ = _make_struct_body(
            struct_name,
            self.model.group_regular[gname],
            self.model.group_nested[gname],
        )
        lines.append(body)
        lines.append("")
        schema_ver = self.provenance.schema_version
        lines.append(_make_schema_version_constant(struct_name, schema_ver))
        lines.append("")
        lines.append(_make_validate_decl(struct_name))
        lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)

    def _build_struct_source_content(self, gname: str, hpp_name: str) -> str:
        """Build the .cpp content for a single struct group."""
        struct_name = self._struct_name if gname == self.model.root else gname
        lines: list[str] = [_make_source_preamble(hpp_name, self.provenance)]
        lines.extend(self._ns_open())
        lines.append("")
        impl = _make_validate_impl(
            struct_name,
            self.model.group_regular[gname],
            self.model.group_nested[gname],
        )
        lines.append(impl)
        lines.append("")
        lines.extend(self._ns_close())
        return "\n".join(lines)
