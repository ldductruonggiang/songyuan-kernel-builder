#!/usr/bin/env python3
"""
Post-Boot Play Integrity Diagnostic Tool for Redmi K100 Pro Max (songyuan)
Evaluates minimum acceptance criteria: BASIC (PASS) + DEVICE (PASS), STRONG (optional).
Outputs: PLAY_INTEGRITY_REPORT.txt
"""

import sys
import subprocess
from pathlib import Path


def run_adb(cmd: str) -> str:
    try:
        res = subprocess.run(["adb", "shell", cmd], capture_output=True, text=True, timeout=8)
        return res.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def run_diagnostic(output_file: str = "PLAY_INTEGRITY_REPORT.txt"):
    print("[*] Running Post-Boot Play Integrity Diagnostic...")

    v_boot = run_adb("getprop ro.boot.verifiedbootstate")
    dev_state = run_adb("getprop ro.boot.vbmeta.device_state")
    flash_locked = run_adb("getprop ro.boot.flash.locked")
    fingerprint = run_adb("getprop ro.build.fingerprint")
    sec_patch = run_adb("getprop ro.build.version.security_patch")
    first_api = run_adb("getprop ro.product.first_api_level")

    report = [
        "==================================================",
        "          PLAY INTEGRITY POST-BOOT REPORT         ",
        "==================================================",
        f"Device:                 Redmi K100 Pro Max (songyuan)",
        f"Verified Boot State:    {v_boot}",
        f"VBMeta Device State:    {dev_state}",
        f"Flash Locked:           {flash_locked}",
        f"Security Patch:         {sec_patch}",
        f"First API Level:        {first_api}",
        f"Fingerprint:            {fingerprint}",
        "--------------------------------------------------",
        "PLAY INTEGRITY ACCEPTANCE TARGETS:",
        "  1. MEETS_BASIC_INTEGRITY:   TARGET = PASS",
        "  2. MEETS_DEVICE_INTEGRITY:  TARGET = PASS",
        "  3. MEETS_STRONG_INTEGRITY:  TARGET = OPTIONAL / BONUS",
        "--------------------------------------------------",
        "EVALUATION STATUS GUIDELINE:",
        "  If BASIC fails: Check ro.debuggable, test-keys, abnormal mounts, or zygote injection.",
        "  If DEVICE fails: Check Play Protect certification, verifiedbootstate spoof, or device profile.",
        "  If BASIC=PASS & DEVICE=PASS: Minimum Play Integrity target is MET.",
        "==================================================",
    ]

    out_text = "\n".join(report)
    Path(output_file).write_text(out_text, encoding="utf-8")
    print(out_text)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "PLAY_INTEGRITY_REPORT.txt"
    run_diagnostic(out)
