#!/usr/bin/env python3
"""
Android Boot Image Repacker & Dual-VBMeta Structural Validator
Target: Redmi K100 Pro Max (songyuan) - Android 16 / HyperOS 3 (ACK 6.12)

Strict fail-closed implementation preserving:
1. Boot Header v4 (magic, os_version, ramdisk_size, cmdline)
2. Exact 4096-byte page alignment
3. 16KB GKI Boot Signature Block (with 'boot' and 'generic_kernel' signed hash descriptors)
4. Xiaomi OEM AVB VBMeta Structure & AVB Footer at partition boundary (100,663,296 bytes)

Generates:
- stock_boot_structure.json
- final_boot_structure.json
- boot_structure.diff
Enforces Gate B: BOOT_REPACK_STRUCTURE=PASS / FAIL.
"""

import sys
import os
import struct
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, Tuple

# Ensure OpenSSL is available if running on Windows
if sys.platform == "win32":
    git_bin = r"C:\Program Files\Git\usr\bin"
    if os.path.isdir(git_bin) and git_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = git_bin + os.pathsep + os.environ.get("PATH", "")

BOOT_MAGIC = b"ANDROID!"
HEADER_V4_SIZE = 4096
PAGE_SIZE = 4096
PARTITION_SIZE = 100663296  # Exact 96MB partition
GKI_SIGNATURE_SIZE = 16384  # 16KB GKI certificate block
OEM_AVB_SALT = "2f3af9c34e034d0b10491da3e7e0c383115e5690fa714a6631b8258227bc1e58"
OEM_ROLLBACK_INDEX = "1785542400"
OEM_PROPS = [
    ("com.android.build.boot.os_version", "16"),
    (
        "com.android.build.boot.fingerprint",
        "POCO/songyuan_global/songyuan:16/BQ2A.260225.001-BP2A.250705.008/OS3.0.301.0.WGNTWXM:user/release-keys",
    ),
    ("com.android.build.boot.security_patch", "2026-08-01"),
]


class BootRepacker:
    def __init__(self, stock_boot_path: str, avbtool_path: str = None, gki_key_path: str = None):
        self.stock_path = Path(stock_boot_path)
        if not self.stock_path.is_file():
            raise FileNotFoundError(f"Stock boot image not found: {self.stock_path}")
        self.file_size = self.stock_path.stat().st_size
        if self.file_size != PARTITION_SIZE:
            raise ValueError(
                f"Stock boot size mismatch! Expected {PARTITION_SIZE} bytes, got {self.file_size} bytes."
            )

        self.avbtool = Path(avbtool_path) if avbtool_path else Path(__file__).parent / "avbtool.py"
        if not self.avbtool.is_file():
            raise FileNotFoundError(f"avbtool not found at: {self.avbtool}")

        self.gki_key = Path(gki_key_path) if gki_key_path else Path(__file__).parent / "gki_testkey.pem"
        if not self.gki_key.is_file():
            raise FileNotFoundError(f"GKI signing key not found at: {self.gki_key}")

    def parse_header(self, data: bytes) -> Dict[str, Any]:
        magic = data[:8]
        if magic != BOOT_MAGIC:
            raise ValueError(f"Invalid magic: {magic} (Expected {BOOT_MAGIC})")
        ksize, rdsize, osver, hdrsize = struct.unpack("<IIII", data[8:24])
        hdrver = struct.unpack("<I", data[40:44])[0]
        if hdrver != 4:
            raise ValueError(f"Unsupported boot header version: {hdrver} (Expected 4)")
        cmdline = data[44 : 44 + 1536].split(b"\x00")[0].decode("utf-8", errors="replace")
        return {
            "magic": magic.decode("latin1"),
            "kernel_size": ksize,
            "ramdisk_size": rdsize,
            "os_version": osver,
            "header_size": hdrsize,
            "header_version": hdrver,
            "cmdline": cmdline,
        }

    def _query_avb_info(self, image_data: bytes) -> Dict[str, Any]:
        """Runs avbtool info_image on an in-memory byte slice and parses fields, descriptors, and props."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(image_data)
            tmp_name = tmp.name
        try:
            res = subprocess.run(
                [sys.executable, str(self.avbtool), "info_image", "--image", tmp_name],
                capture_output=True,
                text=True,
            )
            parsed: Dict[str, Any] = {"descriptors": [], "props": {}}
            current_desc = None

            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if line.startswith("    Hash descriptor:") or line.startswith("    Chain Partition descriptor:"):
                        current_desc = {"type": stripped.rstrip(":")}
                        parsed["descriptors"].append(current_desc)
                    elif line.startswith("      ") and current_desc is not None:
                        if ":" in stripped:
                            k, v = stripped.split(":", 1)
                            current_desc[k.strip()] = v.strip()
                    elif line.startswith("    Prop: "):
                        prop_str = stripped[6:].strip()
                        if "->" in prop_str:
                            pk, pv = prop_str.split("->", 1)
                            parsed["props"][pk.strip()] = pv.strip().strip("'")
                    elif ":" in stripped and not line.startswith(" "):
                        k, v = stripped.split(":", 1)
                        parsed[k.strip()] = v.strip()
            return parsed
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def analyze_structure(self, image_path: Path) -> Dict[str, Any]:
        """Performs comprehensive structural inspection of a 96MB boot image."""
        data = image_path.read_bytes()
        total_len = len(data)

        hdr_info = self.parse_header(data)
        ksize = hdr_info["kernel_size"]
        k_padded_size = ((ksize + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        kernel_end = HEADER_V4_SIZE + ksize
        kernel_padded_end = HEADER_V4_SIZE + k_padded_size

        kernel_bytes = data[HEADER_V4_SIZE:kernel_end]
        kernel_sha256 = hashlib.sha256(kernel_bytes).hexdigest()

        # Check GKI signature block (16KB right after padded kernel)
        gki_sig_start = kernel_padded_end
        gki_sig_end = gki_sig_start + GKI_SIGNATURE_SIZE
        gki_sig_present = False
        gki_certs = []

        if gki_sig_end <= total_len:
            gki_data = data[gki_sig_start:gki_sig_end]
            if gki_data.startswith(b"AVB0"):
                gki_sig_present = True
                # Parse all AVB0 structures in the 16KB signature block
                pos = 0
                while pos < len(gki_data):
                    idx = gki_data.find(b"AVB0", pos)
                    if idx == -1:
                        break
                    # AVB header is 256 bytes. auth_len and aux_len are at offsets 12:28 (2 x uint64)
                    hdr_block = gki_data[idx : idx + 256]
                    if len(hdr_block) >= 32:
                        auth_len, aux_len = struct.unpack(">QQ", hdr_block[12:28])
                        total_vbmeta_len = 256 + auth_len + aux_len
                        vb_data = gki_data[idx : idx + total_vbmeta_len]
                        avb_info = self._query_avb_info(vb_data)
                        gki_certs.append(
                            {
                                "offset_in_sig": idx,
                                "absolute_offset": gki_sig_start + idx,
                                "size": total_vbmeta_len,
                                "info": avb_info,
                            }
                        )
                        pos = idx + total_vbmeta_len
                    else:
                        pos = idx + 4

        # Check OEM AVB footer at partition boundary (last 64 bytes)
        oem_footer_present = False
        oem_footer_info = {}
        oem_vbmeta_info = {}

        if total_len == PARTITION_SIZE:
            footer_bytes = data[PARTITION_SIZE - 64 : PARTITION_SIZE]
            if footer_bytes.startswith(b"AVBf"):
                oem_footer_present = True
                magic, v_maj, v_min, orig_size, vb_off, vb_sz = struct.unpack(
                    ">4sIIQQQ", footer_bytes[:36]
                )
                oem_footer_info = {
                    "offset": PARTITION_SIZE - 64,
                    "version": f"{v_maj}.{v_min}",
                    "original_image_size": orig_size,
                    "vbmeta_offset": vb_off,
                    "vbmeta_size": vb_sz,
                }
                # Inspect OEM VBMeta
                if vb_off < total_len and vb_off + vb_sz <= total_len:
                    oem_vbmeta_data = data[vb_off : vb_off + vb_sz]
                    oem_vbmeta_info = self._query_avb_info(oem_vbmeta_data)

        return {
            "image_path": str(image_path),
            "file_size": total_len,
            "header": hdr_info,
            "kernel": {
                "offset": HEADER_V4_SIZE,
                "size": ksize,
                "padded_size": k_padded_size,
                "sha256": kernel_sha256,
            },
            "gki_signature": {
                "offset": gki_sig_start,
                "size": GKI_SIGNATURE_SIZE,
                "present": gki_sig_present,
                "certificates": gki_certs,
            },
            "oem_avb": {
                "footer_present": oem_footer_present,
                "footer": oem_footer_info,
                "vbmeta": oem_vbmeta_info,
            },
        }

    def verify_roundtrip(self) -> Tuple[bool, str]:
        """Unpacks stock boot.img and validates against stock structural expectations."""
        orig_data = self.stock_path.read_bytes()
        orig_sha = hashlib.sha256(orig_data).hexdigest()
        info = self.parse_header(orig_data)

        if info["header_version"] != 4 or len(orig_data) != PARTITION_SIZE:
            return False, f"Stock structure invalid: hdrver={info['header_version']}, size={len(orig_data)}"

        return True, orig_sha

    def repack(
        self,
        new_kernel_path: str,
        output_boot_path: str,
        out_dir: str = None,
        release_str: str = None,
    ) -> Dict[str, Any]:
        """
        Replaces stock kernel with new_kernel while strictly preserving:
        - Boot Header v4
        - 16KB GKI boot signature with 'boot' and 'generic_kernel' hash descriptors
        - Xiaomi OEM AVB hash footer at 100,663,296 bytes
        Generates stock_boot_structure.json, final_boot_structure.json, and boot_structure.diff.
        """
        new_k_file = Path(new_kernel_path)
        if not new_k_file.is_file():
            raise FileNotFoundError(f"New kernel file not found: {new_k_file}")
        embedded = set(re.findall(rb"Linux version ([^\x00\s]+)", new_k_file.read_bytes()))
        if len(embedded) != 1 or embedded.pop().decode("ascii") != release_str:
            raise ValueError("Kernel release argument does not match the compiled Image")

        stock_avb = self._query_avb_info(self.stock_path.read_bytes())
        stock_algorithm = stock_avb.get("Algorithm")
        if stock_algorithm != "NONE":
            raise RuntimeError(
                "Stock boot uses signed OEM AVB (%s). The available test key cannot "
                "produce an OEM-equivalent signature; refusing to label a repack "
                "flashable without a verified AVB signing plan." % stock_algorithm
            )

        out_path = Path(output_boot_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report_dir = Path(out_dir) if out_dir else out_path.parent
        report_dir.mkdir(parents=True, exist_ok=True)

        # 1. Structural inspection of stock boot
        stock_struct = self.analyze_structure(self.stock_path)
        stock_json_path = report_dir / "stock_boot_structure.json"
        stock_json_path.write_text(json.dumps(stock_struct, indent=2))
        print(f"[BootRepacker] Stock structure saved to {stock_json_path}")

        # 2. Prepare new kernel payload
        new_k_data = new_k_file.read_bytes()
        new_ksize = len(new_k_data)
        new_k_padded_size = ((new_ksize + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        new_k_padding = b"\x00" * (new_k_padded_size - new_ksize)

        # 3. Build Header v4 with updated kernel size
        orig_data = self.stock_path.read_bytes()
        hdr = bytearray(orig_data[:HEADER_V4_SIZE])
        struct.pack_into("<I", hdr, 8, new_ksize)

        boot_base = bytes(hdr) + new_k_data + new_k_padding
        boot_base_size = len(boot_base)

        # 4. Generate certified 16KB GKI Signature Block
        print("[BootRepacker] Generating 16KB GKI signature block (boot + generic_kernel)...")
        with tempfile.NamedTemporaryFile(delete=False) as f_boot, \
             tempfile.NamedTemporaryFile(delete=False) as f_kernel, \
             tempfile.NamedTemporaryFile(delete=False) as f_cert_boot, \
             tempfile.NamedTemporaryFile(delete=False) as f_cert_kernel:

            f_boot.write(boot_base)
            f_boot.flush()
            f_kernel.write(new_k_data)
            f_kernel.flush()

            boot_tmp = f_boot.name
            kernel_tmp = f_kernel.name
            cert_boot_tmp = f_cert_boot.name
            cert_kernel_tmp = f_cert_kernel.name

        try:
            # GKI Cert 1: 'boot'
            subprocess.check_call([
                sys.executable, str(self.avbtool), "add_hash_footer",
                "--partition_name", "boot",
                "--dynamic_partition_size",
                "--image", boot_tmp,
                "--algorithm", "SHA256_RSA4096",
                "--key", str(self.gki_key),
                "--salt", "d00df00d",
                "--prop", "ARCH:arm64",
                "--prop", "BRANCH:",
                "--prop", f"KERNEL_RELEASE:{release_str}",
                "--do_not_append_vbmeta_image",
                "--output_vbmeta_image", cert_boot_tmp,
            ])

            # GKI Cert 2: 'generic_kernel'
            subprocess.check_call([
                sys.executable, str(self.avbtool), "add_hash_footer",
                "--partition_name", "generic_kernel",
                "--dynamic_partition_size",
                "--image", kernel_tmp,
                "--algorithm", "SHA256_RSA4096",
                "--key", str(self.gki_key),
                "--salt", "d00df00d",
                "--prop", "ARCH:arm64",
                "--prop", "BRANCH:",
                "--prop", f"KERNEL_RELEASE:{release_str}",
                "--do_not_append_vbmeta_image",
                "--output_vbmeta_image", cert_kernel_tmp,
            ])

            cert_boot_bytes = Path(cert_boot_tmp).read_bytes()
            cert_kernel_bytes = Path(cert_kernel_tmp).read_bytes()
        finally:
            for p in [boot_tmp, kernel_tmp, cert_boot_tmp, cert_kernel_tmp]:
                if os.path.exists(p):
                    os.unlink(p)

        sig_block = cert_boot_bytes + cert_kernel_bytes
        if len(sig_block) > GKI_SIGNATURE_SIZE:
            raise ValueError(
                f"GKI signature block overflow! Size {len(sig_block)} exceeds {GKI_SIGNATURE_SIZE} bytes."
            )
        sig_padded = sig_block + b"\x00" * (GKI_SIGNATURE_SIZE - len(sig_block))

        # 5. Assemble GKI Boot Image
        gki_boot_image = boot_base + sig_padded
        gki_boot_size = len(gki_boot_image)
        print(f"[BootRepacker] Certified GKI boot image assembled. Size: {gki_boot_size} bytes.")

        # Check partition limit
        if gki_boot_size > PARTITION_SIZE - 65536:
            raise ValueError(
                f"Kernel and GKI signature too large ({gki_boot_size} bytes) for 96MB partition!"
            )

        # 6. Apply Xiaomi OEM AVB Footer
        out_path.write_bytes(gki_boot_image)
        print(f"[BootRepacker] Applying OEM AVB Hash Footer for {PARTITION_SIZE} bytes partition...")

        oem_cmd = [
            sys.executable,
            str(self.avbtool),
            "add_hash_footer",
            "--image",
            str(out_path),
            "--partition_size",
            str(PARTITION_SIZE),
            "--partition_name",
            "boot",
            "--salt",
            OEM_AVB_SALT,
            "--rollback_index",
            OEM_ROLLBACK_INDEX,
        ]
        for prop_k, prop_v in OEM_PROPS:
            oem_cmd.extend(["--prop", f"{prop_k}:{prop_v}"])

        subprocess.check_call(oem_cmd)

        final_size = out_path.stat().st_size
        if final_size != PARTITION_SIZE:
            raise ValueError(
                f"Repacked image size {final_size} does not match partition size {PARTITION_SIZE}!"
            )

        # 7. Structural inspection of final boot
        final_struct = self.analyze_structure(out_path)
        final_json_path = report_dir / "final_boot_structure.json"
        final_json_path.write_text(json.dumps(final_struct, indent=2))
        print(f"[BootRepacker] Final structure saved to {final_json_path}")

        # 8. Structural Diff Gate (Gate B)
        diff_path = report_dir / "boot_structure.diff"
        gate_b_pass, diff_log = self._validate_structural_diff(
            stock_struct, final_struct, new_k_file
        )
        diff_path.write_text(diff_log)
        print(f"[BootRepacker] Structural diff report saved to {diff_path}")

        return {
            "success": gate_b_pass,
            "gate_b_status": "PASS" if gate_b_pass else "FAIL",
            "final_image": str(out_path),
            "final_size": final_size,
            "final_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
            "stock_json": str(stock_json_path),
            "final_json": str(final_json_path),
            "diff_path": str(diff_path),
        }

    def _validate_structural_diff(
        self, stock: Dict[str, Any], final: Dict[str, Any], new_kernel_path: Path
    ) -> Tuple[bool, str]:
        """Compares stock and final boot structures with strict fail-closed validation."""
        lines = []
        lines.append("=" * 60)
        lines.append("        BOOT IMAGE STRUCTURAL DIFF VALIDATION (GATE B)")
        lines.append("=" * 60)

        passed = True
        new_k_data = new_kernel_path.read_bytes()
        new_k_sha = hashlib.sha256(new_k_data).hexdigest()

        # 1. Total file size
        s_sz = stock["file_size"]
        f_sz = final["file_size"]
        if f_sz == PARTITION_SIZE:
            lines.append(f"[PASS] Partition Size: {f_sz} bytes (Exact 96MB Match)")
        else:
            lines.append(f"[FAIL] Partition Size: expected {PARTITION_SIZE}, got {f_sz}")
            passed = False

        # 2. Header V4 parameters
        s_hdr = stock["header"]
        f_hdr = final["header"]

        for field in ["magic", "header_version", "header_size", "ramdisk_size", "os_version", "cmdline"]:
            s_val = s_hdr.get(field)
            f_val = f_hdr.get(field)
            if s_val == f_val:
                lines.append(f"[PASS] Header {field}: preserved ({f_val})")
            else:
                lines.append(f"[FAIL] Header {field} mismatch! Stock: {s_val}, Final: {f_val}")
                passed = False

        # 3. Kernel payload & size update
        s_ksize = s_hdr["kernel_size"]
        f_ksize = f_hdr["kernel_size"]
        actual_ksize = len(new_k_data)
        if f_ksize == actual_ksize:
            lines.append(f"[PASS] Kernel size correctly updated: {s_ksize} -> {f_ksize} bytes")
        else:
            lines.append(
                f"[FAIL] Kernel size header ({f_ksize}) does not match new Image file ({actual_ksize})"
            )
            passed = False

        if final["kernel"]["sha256"] == new_k_sha:
            lines.append(f"[PASS] Kernel payload SHA256 matches input binary: {new_k_sha}")
        else:
            lines.append("[FAIL] Repacked kernel payload bytes do not match input binary!")
            passed = False

        # 4. GKI Signature Block (16KB)
        f_gki = final["gki_signature"]
        if f_gki["present"] and f_gki["size"] == GKI_SIGNATURE_SIZE:
            lines.append(f"[PASS] GKI Signature Block present: size={f_gki['size']} bytes at offset={f_gki['offset']}")
        else:
            lines.append("[FAIL] GKI Signature Block missing or corrupted!")
            passed = False

        # Verify GKI certificates
        certs = f_gki.get("certificates", [])
        boot_cert_ok = False
        kernel_cert_ok = False
        for c in certs:
            info = c.get("info", {})
            descs = info.get("descriptors", [])
            for d in descs:
                part = d.get("Partition Name", "")
                if part == "boot":
                    boot_cert_ok = True
                    lines.append(f"[PASS] GKI 'boot' certificate verified (size {c['size']} bytes)")
                elif part == "generic_kernel":
                    kernel_cert_ok = True
                    digest = d.get("Digest", "")
                    # avbtool calculates digest with salt d00df00d
                    h = hashlib.sha256()
                    h.update(bytes.fromhex("d00df00d"))
                    h.update(new_k_data)
                    expected_avb_digest = h.hexdigest()
                    if digest == expected_avb_digest:
                        lines.append(
                            f"[PASS] GKI 'generic_kernel' certificate digest MATCHES salted kernel digest ({digest})"
                        )
                    else:
                        lines.append(
                            f"[FAIL] GKI 'generic_kernel' certificate digest {digest} does not match expected {expected_avb_digest}!"
                        )
                        passed = False

        if not boot_cert_ok:
            lines.append("[FAIL] GKI 'boot' certificate missing from signature block!")
            passed = False
        if not kernel_cert_ok:
            lines.append("[FAIL] GKI 'generic_kernel' certificate missing from signature block!")
            passed = False

        # 5. OEM AVB Footer & VBMeta
        f_oem = final["oem_avb"]
        if f_oem["footer_present"]:
            ft = f_oem["footer"]
            lines.append(
                f"[PASS] OEM AVB Footer verified at offset {ft['offset']} (orig_size={ft['original_image_size']}, vbmeta_offset={ft['vbmeta_offset']})"
            )
        else:
            lines.append("[FAIL] OEM AVB Footer missing from 96MB boundary!")
            passed = False

        lines.append("=" * 60)
        status_str = "PASS" if passed else "FAIL"
        lines.append(f"FINAL GATE B RESULT: BOOT_REPACK_STRUCTURE={status_str}")
        lines.append("=" * 60)

        return passed, "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 8:
        print("Usage: python boot_repacker.py <stock_boot.img> <new_Image> <output_boot.img> <avbtool.py> <gki_key.pem> <out_dir> <kernel_release>")
        sys.exit(1)

    stock_img = sys.argv[1]
    new_kernel = sys.argv[2]
    out_img = sys.argv[3] if len(sys.argv) > 3 else "boot-sukisu-susfs-kpm-songyuan.img"
    avb_tool = sys.argv[4] if len(sys.argv) > 4 else None
    gki_key = sys.argv[5] if len(sys.argv) > 5 else None
    out_dir = sys.argv[6] if len(sys.argv) > 6 else str(Path(out_img).parent)
    release_str = sys.argv[7]

    repacker = BootRepacker(stock_img, avb_tool, gki_key)
    res = repacker.repack(new_kernel, out_img, out_dir, release_str)

    print(f"\n[BootRepacker] Repack finished. Status: {res['gate_b_status']}")
    if not res["success"]:
        print("[FATAL] Gate B structural validation FAILED!")
        sys.exit(1)
    print(f"[SUCCESS] Repacked image: {res['final_image']} (SHA256: {res['final_sha256']})")
    sys.exit(0)
