#!/usr/bin/env python3
"""
Post-Boot BShield & Stealth Hardening Diagnostic Tool for Redmi K100 Pro Max (songyuan)
Queries live device properties via ADB and audits against BShield detection criteria.
Outputs: BSHIELD_DIAGNOSTIC_REPORT.txt
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


def run_diagnostic(output_file: str = "BSHIELD_DIAGNOSTIC_REPORT.txt"):
    print("[*] Running Post-Boot BShield Hardening Diagnostic...")

    selinux = run_adb("getenforce")
    uname_r = run_adb("uname -r")
    debuggable = run_adb("getprop ro.debuggable")
    secure = run_adb("getprop ro.secure")
    adb_root = run_adb("getprop service.adb.root")
    init_adb_root = run_adb("getprop init.svc.adb_root")
    build_keys = run_adb("getprop ro.build.keys")
    display_id = run_adb("getprop ro.build.display.id")

    # Mount audit
    mounts = run_adb("cat /proc/mounts")
    suspicious_mounts = []
    for line in mounts.splitlines():
        if any(term in line.lower() for term in ["magisk", "ksu", "apatch", "overlay", "tmpfs /system"]):
            suspicious_mounts.append(line)

    # Verification checks
    selinux_pass = (selinux.lower() == "enforcing")
    dirty_pass = ("-dirty" not in uname_r)
    release_pass = (uname_r == "6.12.69-android16-6-g0d80ee00f747-ab15461283-4k")
    debug_pass = (debuggable != "1" and adb_root != "1" and init_adb_root != "running")
    test_keys_pass = ("test-keys" not in build_keys and "test-keys" not in display_id)
    mounts_pass = (len(suspicious_mounts) == 0)

    report = [
        "==================================================",
        "      BSHIELD HARDENING POST-BOOT DIAGNOSTIC      ",
        "==================================================",
        f"SELINUX:                 {'PASS' if selinux_pass else 'FAIL'} ({selinux})",
        f"KERNEL_RELEASE:          {'PASS' if release_pass else 'FAIL'} ({uname_r})",
        f"DIRTY_FLAG:              {'PASS' if dirty_pass else 'FAIL'}",
        f"DEBUG_PROPERTIES:        {'PASS' if debug_pass else 'FAIL'}",
        f"RELEASE_KEYS:            {'PASS' if test_keys_pass else 'FAIL'}",
        f"SUSPICIOUS_MOUNTS:       {'PASS' if mounts_pass else 'FAIL'} ({len(suspicious_mounts)} detected)",
        "--------------------------------------------------",
        "Audit Details:",
        f"  ro.debuggable:         {debuggable}",
        f"  ro.secure:             {secure}",
        f"  service.adb.root:      {adb_root}",
        f"  ro.build.keys:         {build_keys}",
        f"  ro.build.display.id:   {display_id}",
        "--------------------------------------------------",
    ]

    if suspicious_mounts:
        report.append("Detected Suspicious Mounts:")
        for m in suspicious_mounts[:10]:
            report.append(f"  * {m}")
        report.append("--------------------------------------------------")

    overall = all([selinux_pass, dirty_pass, release_pass, debug_pass, test_keys_pass])
    report.append(f"OVERALL BSHIELD COMPLIANCE: {'PASS' if overall else 'FAIL'}")
    report.append("==================================================")

    out_text = "\n".join(report)
    Path(output_file).write_text(out_text, encoding="utf-8")
    print(out_text)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "BSHIELD_DIAGNOSTIC_REPORT.txt"
    run_diagnostic(out)
