#!/usr/bin/env python3
"""Extract real modversion CRCs and vermagic from ROM .ko files."""

import argparse
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path

from elftools.elf.elffile import ELFFile


def read_module(path: Path):
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if elf.elfclass != 64 or not elf.little_endian:
            raise ValueError(f"Unsupported ELF format: {path}")
        names_section = elf.get_section_by_name("__version_ext_names")
        crcs_section = elf.get_section_by_name("__version_ext_crcs")
        modinfo = elf.get_section_by_name(".modinfo")
        if not all((names_section, crcs_section, modinfo)):
            raise ValueError(f"Missing modversion or modinfo sections: {path}")
        names = names_section.data().rstrip(b"\0").split(b"\0")
        crcs = crcs_section.data()
        if not names or len(crcs) != 4 * len(names):
            raise ValueError(f"Invalid modversion table: {path}")
        magic = [
            item.decode("ascii") for item in modinfo.data().split(b"\0")
            if item.startswith(b"vermagic=")
        ]
        if len(magic) != 1:
            raise ValueError(f"Missing or ambiguous vermagic: {path}")
        versions = {
            name.decode("ascii"): f"0x{struct.unpack_from('<I', crcs, index * 4)[0]:08x}"
            for index, name in enumerate(names)
        }
        if len(versions) != len(names):
            raise ValueError(f"Duplicate symbol in module: {path}")
        symbol_table = elf.get_section_by_name(".symtab")
        if symbol_table is None:
            raise ValueError(f"Missing ELF symbol table: {path}")
        exports = {}
        for symbol in symbol_table.iter_symbols():
            if not symbol.name.startswith("__crc_") or not isinstance(symbol["st_shndx"], int):
                continue
            section = elf.get_section(symbol["st_shndx"])
            if not section.name.startswith("__kcrctab"):
                continue
            crc = struct.unpack_from("<I", section.data(), symbol["st_value"])[0]
            exports[symbol.name.removeprefix("__crc_")] = f"0x{crc:08x}"
        return magic[0].removeprefix("vermagic="), versions, exports


def generate(directories: list[Path]):
    symbols = defaultdict(lambda: defaultdict(set))
    providers = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    imports = []
    magics = defaultdict(Counter)
    module_count = Counter()
    for directory in directories:
        files = sorted(directory.rglob("*.ko"))
        if not files:
            raise ValueError(f"No .ko files found: {directory}")
        for path in files:
            magic, versions, exports = read_module(path)
            partition = directory.name
            owner = f"{partition}/{path.relative_to(directory).as_posix()}"
            module_count[partition] += 1
            magics[partition][magic] += 1
            for symbol, crc in versions.items():
                imports.append((partition, owner, symbol, crc))
            for symbol, crc in exports.items():
                providers[partition][symbol][crc].add(owner)

    module_mismatches = []
    for partition, owner, symbol, crc in imports:
        local = providers[partition].get(symbol)
        other = [item for part, group in providers.items() if part != partition
                 for item in [group.get(symbol)] if item]
        provided = local or (other[0] if len(other) == 1 else None)
        if provided:
            if crc not in provided:
                module_mismatches.append({
                    "module": owner, "symbol": symbol, "expected_crc": crc,
                    "provider_crcs": sorted(provided),
                })
        else:
            symbols[symbol][crc].add(owner)

    reference = {}
    for name, crcs in sorted(symbols.items()):
        owners = sorted({owner for group in crcs.values() for owner in group})
        if len(crcs) == 1:
            reference[name] = {"crc": next(iter(crcs)), "required_by": owners}
        else:
            reference[name] = {
                "crc": "",
                "required_by": owners,
                "conflicting_crcs": {crc: sorted(group) for crc, group in sorted(crcs.items())},
            }
    metadata = {
        "module_count": dict(module_count),
        "vermagic": {part: dict(values) for part, values in magics.items()},
        "symbol_count": len(reference),
        "conflicting_symbols": [name for name, info in reference.items() if not info["crc"]],
        "module_dependency_mismatches": module_mismatches,
    }
    return reference, metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor_dlkm", type=Path)
    parser.add_argument("system_dlkm", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    reference, metadata = generate([args.vendor_dlkm, args.system_dlkm])
    args.reference.write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))
