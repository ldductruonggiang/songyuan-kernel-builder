"""
songyuan-sukisu-builder: Main Application Entrypoint
Redmi K100 Pro Max (songyuan) SukiSU Ultra Built-in Kernel Engine
"""

import sys
import argparse
from pathlib import Path

from src.device_detector import DeviceDetector
from src.source_detector import SourceDetector
from src.boot_analyzer import BootAnalyzer
from src.abi_validator import AbiValidator


def run_cli_detect():
    print("=" * 60)
    print("  Redmi K100 Pro Max (songyuan) - Hardware & Firmware Audit")
    print("=" * 60)
    detector = DeviceDetector()
    info = detector.detect_device_adb()

    for k, v in info.items():
        print(f"  {k:<24}: {v}")
    print("=" * 60)


def run_cli_check_source():
    print("=" * 60)
    print("  5-Tier Kernel Source Hierarchy & Safety Verification")
    print("=" * 60)
    detector = SourceDetector()
    status = detector.determine_source_status()

    print(f"Status:        {status['status'].value}")
    print(f"Can Flash:     {status['can_flash']}")
    print(f"Can Auto-Build:{status['can_auto_build']}")
    print(f"Reason:        {status['reason']}\n")

    print("Evaluated Candidates:")
    for c in status["candidates"]:
        print(f"  [Tier {c['tier']}] {c['name']:<30} -> {c['status']}")
    print("=" * 60)


def run_cli_verify_boot(boot_path: str):
    print(f"Verifying boot image: {boot_path}")
    analyzer = BootAnalyzer(boot_path)
    res = analyzer.analyze()
    if res["valid"]:
        print("[SUCCESS] Valid Android Boot Header v{}".format(res["header_version"]))
        print(f"  Kernel Size:    {res['kernel_size']} bytes")
        print(f"  Ramdisk Size:   {res['ramdisk_size']} bytes")
        print(f"  OS Version:     {res['os_version']}")
        print(f"  Security Patch: {res['os_patch_level']}")
        print(f"  Header Size:    {res['header_size']} bytes")
        print(f"  SHA256:         {res['sha256']}")
    else:
        print(f"[FAIL] Boot image invalid: {res.get('error')}")


def main():
    parser = argparse.ArgumentParser(
        description="SukiSU Ultra Built-in Kernel Builder & Flasher for Redmi K100 Pro Max (songyuan)"
    )
    parser.add_argument("--cli", action="store_true", help="Run in Command-Line Interface mode")
    parser.add_argument("--detect", action="store_true", help="Detect connected device parameters via ADB / Fastboot")
    parser.add_argument("--check-source", action="store_true", help="Inspect and validate kernel source repositories")
    parser.add_argument("--verify-boot", type=str, help="Verify Android Boot Header v3/v4 of a boot.img")
    parser.add_argument("--gui", action="store_true", help="Launch PySide6 Graphical Dashboard (Default)")

    args = parser.parse_args()

    # Route CLI actions
    if args.detect:
        run_cli_detect()
        return
    if args.check_source:
        run_cli_check_source()
        return
    if args.verify_boot:
        run_cli_verify_boot(args.verify_boot)
        return

    # If --cli specified with no specific command, run standard audit
    if args.cli:
        run_cli_detect()
        print()
        run_cli_check_source()
        return

    # Default: launch GUI
    try:
        from src.gui import launch_gui
        launch_gui()
    except Exception as e:
        print(f"[ERROR] Could not start GUI: {e}", file=sys.stderr)
        print("Falling back to CLI diagnostic mode:")
        run_cli_detect()


if __name__ == "__main__":
    main()
