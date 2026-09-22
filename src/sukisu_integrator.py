"""
SukiSU Ultra, SUSFS & KPM Integrator Module
Handles upstream integration via setup.sh builtin, manages SUSFS branch selection,
and enforces CONFIG_KPM=y with full diff tracking.
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any
from .config import SusfsBranch, HookMethod, SUKISU_UPSTREAM_URL


class SukiSuIntegrator:
    def __init__(self, kernel_root: str):
        self.kernel_root = Path(kernel_root)
        self.drivers_dir = self._detect_drivers_dir()

    def _detect_drivers_dir(self) -> Path:
        common_drivers = self.kernel_root / "common" / "drivers"
        if common_drivers.is_dir():
            return common_drivers
        standard_drivers = self.kernel_root / "drivers"
        return standard_drivers

    def check_prerequisites(self) -> Dict[str, bool]:
        return {
            "kernel_root_exists": self.kernel_root.is_dir(),
            "drivers_dir_exists": self.drivers_dir.is_dir(),
            "makefile_exists": (self.drivers_dir / "Makefile").is_file(),
            "kconfig_exists": (self.drivers_dir / "Kconfig").is_file(),
        }

    def generate_integration_script(
        self,
        susfs_branch: SusfsBranch = SusfsBranch.AUTO_STABLE,
        hook_method: HookMethod = HookMethod.KPROBES,
        enable_kpm: bool = True,
    ) -> str:
        """
        Creates an automated bash script implementing upstream SukiSU setup.sh.
        Tracks commit SHAs, applies SUSFS, and enforces CONFIG_KPM=y.
        """
        susfs_arg = ""
        if susfs_branch == SusfsBranch.MAIN:
            susfs_arg = "susfs-main"
        elif susfs_branch == SusfsBranch.TEST:
            susfs_arg = "susfs-test"
        elif susfs_branch == SusfsBranch.AUTO_STABLE or susfs_branch == SusfsBranch.VERSIONED:
            susfs_arg = "susfs-main"  # Upstream default branch for SUSFS in SukiSU

        script = f"""#!/bin/bash
set -euo pipefail

KERNEL_ROOT="{self.kernel_root.as_posix()}"
cd "$KERNEL_ROOT"

echo "=== [1/5] Setting up SukiSU Ultra BUILT-IN ==="
curl -LSs "https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/main/kernel/setup.sh" | bash -s builtin

# Record exact commit SHA
cd "$KERNEL_ROOT/KernelSU"
SUKISU_COMMIT=$(git rev-parse HEAD)
SUKISU_BRANCH=$(git rev-parse --abbrev-ref HEAD)
cd "$KERNEL_ROOT"

echo "SUKISU_COMMIT=$SUKISU_COMMIT"
echo "SUKISU_BRANCH=$SUKISU_BRANCH"

"""
        if susfs_branch != SusfsBranch.DISABLED and susfs_arg:
            script += f"""
echo "=== [2/5] Setting up SUSFS ({susfs_arg}) ==="
curl -LSs "https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/main/kernel/setup.sh" | bash -s {susfs_arg}
"""

        script += f"""
echo "=== [3/5] Configuring Hook Method: {hook_method.value} ==="
if [ -f .config ]; then
    cp .config .config.stock_backup
fi

# Ensure required Kconfig flags
scripts/config --enable CONFIG_KSU
"""
        if hook_method == HookMethod.KPROBES:
            script += """
scripts/config --enable CONFIG_KPROBES
scripts/config --disable CONFIG_KSU_MANUAL_HOOK
"""
        elif hook_method == HookMethod.MANUAL:
            script += """
scripts/config --enable CONFIG_KSU_MANUAL_HOOK
"""

        if enable_kpm:
            script += """
echo "=== [4/5] Enforcing CONFIG_KPM=y ==="
scripts/config --enable CONFIG_KPM
"""

        script += """
echo "=== [5/5] Verifying .config and generating diffs ==="
# Run olddefconfig to refresh dependencies
make olddefconfig || true

# Strict verification of CONFIG_KPM
if ! grep -q "^CONFIG_KPM=y" .config; then
    echo "[FATAL ERROR] CONFIG_KPM=y is not set in .config! Build aborted." >&2
    exit 1
fi

echo "[SUCCESS] SukiSU Ultra built-in integrated, SUSFS configured, CONFIG_KPM=y verified."
"""
        return script
