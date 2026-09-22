"""
songyuan-sukisu-builder: Core Configuration & Safety Constraints
Target: Redmi K100 Pro Max (songyuan) / Snapdragon 8 Elite / Android 16 / GKI 6.12
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class SourceStatus(str, Enum):
    EXACT_DEVICE_SOURCE = "EXACT_DEVICE_SOURCE"
    GKI_COMPATIBLE_SOURCE = "GKI_COMPATIBLE_SOURCE"
    PARTIAL_SOURCE = "PARTIAL_SOURCE"
    UNKNOWN = "UNKNOWN"


class HookMethod(str, Enum):
    KPROBES = "KPROBES"
    TRACEPOINT = "TRACEPOINT"
    MANUAL = "MANUAL"


class SusfsBranch(str, Enum):
    AUTO_STABLE = "Auto Stable"
    MAIN = "susfs-main"
    VERSIONED = "Versioned"
    TEST = "susfs-test"
    DISABLED = "Disabled"


@dataclass(frozen=True)
class TargetDeviceSpecs:
    codename: str = "songyuan"
    manufacturer: str = "Xiaomi"
    expected_models: tuple = ("26077PC53G", "Redmi K100 Pro Max")
    android_version: int = 16
    kernel_base: str = "6.12"
    expected_kmi: str = "android16-6.12"
    expected_page_size: int = 4096
    boot_header_version: int = 4
    target_flash_partition: str = "boot"


# Safety blacklist: partitions that MUST NEVER be erased or flashed
RESTRICTED_PARTITIONS = frozenset(
    {
        "userdata",
        "persist",
        "modem",
        "modemst1",
        "modemst2",
        "fsg",
        "fsc",
        "efs",
        "frp",
        "metadata",
        "vbmeta",
        "vbmeta_system",
        "vbmeta_vendor",
        "secdata",
        "devinfo",
    }
)

SUKISU_UPSTREAM_URL = "https://github.com/SukiSU-Ultra/SukiSU-Ultra"
SUKISU_SETUP_SCRIPT_URL = (
    "https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/main/kernel/setup.sh"
)
