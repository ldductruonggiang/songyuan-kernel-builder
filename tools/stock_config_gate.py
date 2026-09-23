#!/usr/bin/env python3
"""Require boot-critical stock settings to survive the final Kleaf build."""

import sys
from pathlib import Path


REQUIRED = (
    "CONFIG_ARM64_4K_PAGES",
    "CONFIG_MODVERSIONS",
    "CONFIG_RUST",
    "CONFIG_TRIM_UNUSED_KSYMS",
    "CONFIG_MODULE_SIG_PROTECT",
    "CONFIG_SECURITY_SELINUX",
)


def options(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line[2:].split(" ", 1)[0]] = "n"
    return result


def check(stock_path: Path, built_path: Path) -> list[str]:
    stock, built = options(stock_path), options(built_path)
    return [
        f"{key}: stock={stock.get(key, 'UNKNOWN')} built={built.get(key, 'UNKNOWN')}"
        for key in REQUIRED
        if stock.get(key) is None or built.get(key) != stock[key]
    ]


if __name__ == "__main__":
    try:
        problems = check(Path(sys.argv[1]), Path(sys.argv[2]))
    except (IndexError, OSError) as exc:
        print(f"FATAL: cannot compare stock and final configs: {exc}", file=sys.stderr)
        sys.exit(1)
    if problems:
        print("FATAL: stock config compatibility failed:\n" + "\n".join(problems), file=sys.stderr)
        sys.exit(1)
    print("Stock config gate passed")
