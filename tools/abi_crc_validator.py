#!/usr/bin/env python3
"""
ABI & Symbol CRC Gate Validator for Redmi K100 Pro Max (songyuan)
Compares Module.symvers against stock vendor_symbol_crc_reference.json
Enforces fail-closed rules: FLASHABLE=YES only if all critical symbols match and release string matches.
"""

import sys
import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List

EXPECTED_RELEASE = "6.12.69-android16-6-g0d80ee00f747-ab15461283-4k"

# Critical modules that would cause immediate panic / failure to boot if CRC mismatches
CRITICAL_MODULES = [
    "ufs-qcom.ko",
    "sc96281_charger.ko",
    "qti_pmic_glink.ko",
    "qcom_glink.ko",
    "zram.ko",
    "synx-driver.ko",
    "xiaomi_touch.ko",
    "msm_drm.ko",
    "msm_kgsl.ko",
]


def parse_module_symvers(symvers_path: Path) -> Dict[str, str]:
    """
    Parses Module.symvers:
    <CRC>\t<symbol_name>\t<module_path>\t<export_type>\t<namespace>
    """
    syms = {}
    if not symvers_path.is_file():
        raise FileNotFoundError(f"Module.symvers not found: {symvers_path}")

    with open(symvers_path, "r", errors="ignore") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                crc_str = parts[0].strip()
                name = parts[1].strip()
                # normalize CRC to hex string
                try:
                    crc_int = int(crc_str, 16)
                    syms[name] = f"{crc_int:#010x}"
                except ValueError:
                    syms[name] = crc_str.lower()
    return syms


def validate(
    symvers_file: str,
    reference_json: str,
    kernel_release_str: str,
    output_report_file: str = "abi-report.txt",
    module_metadata_file: str = None,
) -> Dict[str, Any]:
    symvers_path = Path(symvers_file)
    ref_path = Path(reference_json)
    out_path = Path(output_report_file)

    if not ref_path.is_file():
        raise FileNotFoundError(f"Reference JSON not found: {ref_path}")

    with open(ref_path, "r") as f:
        reference = json.load(f)
    metadata = None
    if module_metadata_file:
        metadata = json.loads(Path(module_metadata_file).read_text(encoding="utf-8"))
        if metadata.get("symbol_count") != len(reference):
            raise ValueError("Module metadata symbol count does not match CRC reference")
        counts = metadata.get("module_count", {})
        if not counts.get("vendor_dlkm") or not counts.get("system_dlkm"):
            raise ValueError("CRC reference lacks vendor_dlkm or system_dlkm modules")
    invalid_reference = [
        name for name, info in reference.items()
        if not re.fullmatch(r"0x[0-9a-fA-F]{8}", str(info.get("crc", "")))
    ]

    built_syms = parse_module_symvers(symvers_path)
    clean_release = kernel_release_str.strip()

    has_dirty = "-dirty" in clean_release
    release_match = clean_release == EXPECTED_RELEASE

    # 2. Symbol comparison
    matched = []
    mismatched = []
    missing = []
    critical_failures = []

    for sym_name, info in reference.items():
        expected_crc = str(info.get("crc", "")).lower()
        req_by = info.get("required_by", [])
        is_critical = any(Path(module).name in CRITICAL_MODULES for module in req_by)

        if sym_name not in built_syms:
            missing.append((sym_name, req_by))
            if is_critical:
                critical_failures.append(f"MISSING: {sym_name} (Required by {req_by[:2]})")
        else:
            built_crc = built_syms[sym_name].lower()
            if built_crc == expected_crc:
                matched.append(sym_name)
            else:
                mismatched.append((sym_name, expected_crc, built_crc, req_by))
                if is_critical:
                    critical_failures.append(
                        f"MISMATCH: {sym_name} expected {expected_crc} got {built_crc} (Required by {req_by[:2]})"
                    )

    total_ref = len(reference)
    match_pct = (len(matched) / total_ref * 100) if total_ref > 0 else 0

    # Determine flashable
    # A missing vendor symbol is an unknown ABI result, not evidence of compatibility.
    flashable = (
        release_match
        and not has_dirty
        and total_ref > 0
        and not invalid_reference
        and len(critical_failures) == 0
        and len(mismatched) == 0
        and len(missing) == 0
        and (metadata is None or not metadata.get("module_dependency_mismatches")
             and not metadata.get("conflicting_symbols"))
    )

    report_lines = [
        "==================================================",
        "  SONGYUAN KERNEL ABI & SYMBOL CRC AUDIT REPORT   ",
        "==================================================",
        f"Device:                 Redmi K100 Pro Max (songyuan)",
        f"Target ROM:             OS3.0.301.0.WGNTWXM",
        f"Stock Release:          {EXPECTED_RELEASE}",
        f"Built Release:          {clean_release}",
        f"Release Match:          {'PASS' if release_match else 'FAIL'}",
        f"Dirty Flag Check:       {'FAIL (-dirty detected)' if has_dirty else 'PASS (clean)'}",
        "--------------------------------------------------",
        f"Total Reference Syms:   {total_ref}",
        f"Invalid Reference CRCs: {len(invalid_reference)}",
        f"Stock Vendor Modules:    {metadata['module_count']['vendor_dlkm'] if metadata else 'UNKNOWN'}",
        f"Stock System Modules:    {metadata['module_count']['system_dlkm'] if metadata else 'UNKNOWN'}",
        f"Module Dependencies:     {len(metadata['module_dependency_mismatches']) if metadata else 'UNKNOWN'} mismatches",
        f"Matched Symbols:        {len(matched)} ({match_pct:.2f}%)",
        f"Mismatched Symbols:     {len(mismatched)}",
        f"Missing Symbols:        {len(missing)}",
        f"Critical Module Errors: {len(critical_failures)}",
        "--------------------------------------------------",
    ]

    if critical_failures:
        report_lines.append("[CRITICAL MODULE FAILURES]")
        for cf in critical_failures[:20]:
            report_lines.append(f"  * {cf}")
        if len(critical_failures) > 20:
            report_lines.append(f"  ... and {len(critical_failures) - 20} more.")
        report_lines.append("--------------------------------------------------")

    if invalid_reference:
        report_lines.append("[INVALID STOCK CRC REFERENCE]")
        report_lines.extend(f"  * {name}" for name in invalid_reference[:10])
        report_lines.append("--------------------------------------------------")

    if metadata:
        report_lines.append("[STOCK MODULE VERMAGIC]")
        for partition, variants in metadata.get("vermagic", {}).items():
            for magic, count in variants.items():
                report_lines.append(f"  * {partition}: {count} modules, {magic}")
        report_lines.append("--------------------------------------------------")

    if mismatched:
        report_lines.append("[TOP MISMATCHES]")
        for sym, exp, act, mod in mismatched[:10]:
            report_lines.append(f"  * {sym}: expected {exp}, got {act} (used by {mod[:2]})")
        report_lines.append("--------------------------------------------------")

    verdict = "YES" if flashable else "NO"
    report_lines.append(f"FINAL ABI STATUS: FLASHABLE={verdict}")
    report_lines.append("==================================================")

    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))

    return {
        "flashable": flashable,
        "release_match": release_match,
        "dirty": has_dirty,
        "total_ref": total_ref,
        "matched": len(matched),
        "mismatched": len(mismatched),
        "missing": len(missing),
        "critical_errors": len(critical_failures),
        "invalid_reference": len(invalid_reference),
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python abi_crc_validator.py <Module.symvers> <vendor_reference.json> <kernel_release_str> [output_report.txt] [module_metadata.json]")
        sys.exit(1)

    symvers = sys.argv[1]
    ref_json = sys.argv[2]
    rel_str = sys.argv[3]
    out_rep = sys.argv[4] if len(sys.argv) > 4 else "abi-report.txt"
    metadata_file = sys.argv[5] if len(sys.argv) > 5 else None

    res = validate(symvers, ref_json, rel_str, out_rep, metadata_file)
    if not res["flashable"]:
        print("[WARNING] ABI Gate check did not achieve FLASHABLE=YES!")
        sys.exit(2)
    else:
        print("[SUCCESS] ABI Gate passed! FLASHABLE=YES")
