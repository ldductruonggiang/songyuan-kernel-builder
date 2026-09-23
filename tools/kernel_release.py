#!/usr/bin/env python3
"""Read the release compiled into an arm64 Image; never infer it from metadata."""

import re
import sys
from pathlib import Path


def read_release(path: Path) -> str:
    data = path.read_bytes()
    matches = set(re.findall(rb"Linux version ([^\x00\s]+)", data))
    if len(matches) != 1:
        raise ValueError(f"Expected one embedded Linux release, found {len(matches)}")
    return matches.pop().decode("ascii")


if __name__ == "__main__":
    try:
        print(read_release(Path(sys.argv[1])))
    except (IndexError, OSError, UnicodeError, ValueError) as exc:
        print(f"FATAL: cannot verify embedded kernel release: {exc}", file=sys.stderr)
        sys.exit(1)
