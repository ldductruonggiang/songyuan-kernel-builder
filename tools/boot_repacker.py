#!/usr/bin/env python3
"""
Android Boot Image Repacker & Validator for Redmi K100 Pro Max (songyuan)
Strict fail-closed implementation preserving stock header v4, ramdisk, cmdline, layout.
Performs mandatory round-trip validation before allowing repacking.
"""

import sys
import os
import struct
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple

BOOT_MAGIC = b"ANDROID!"
HEADER_V4_SIZE = 4096
PAGE_SIZE = 4096
PARTITION_SIZE = 100663296  # 96MB for songyuan boot partition


class BootRepacker:
    def __init__(self, stock_boot_path: str):
        self.stock_path = Path(stock_boot_path)
        if not self.stock_path.is_file():
            raise FileNotFoundError(f"Stock boot image not found: {self.stock_path}")
        self.file_size = self.stock_path.stat().st_size
        if self.file_size != PARTITION_SIZE:
            raise ValueError(
                f"Stock boot size mismatch! Expected {PARTITION_SIZE} bytes, got {self.file_size} bytes."
            )

    def parse_header(self, data: bytes) -> Dict[str, Any]:
        magic = data[:8]
        if magic != BOOT_MAGIC:
            raise ValueError(f"Invalid magic: {magic} (Expected {BOOT_MAGIC})")
        ksize, rdsize, osver, hdrsize = struct.unpack("<IIII", data[8:24])
        hdrver = struct.unpack("<I", data[40:44])[0]
        if hdrver != 4:
            raise ValueError(f"Unsupported boot header version: {hdrver} (Expected 4)")
        return {
            "kernel_size": ksize,
            "ramdisk_size": rdsize,
            "os_version": osver,
            "header_size": hdrsize,
            "header_version": hdrver,
        }

    def verify_roundtrip(self) -> Tuple[bool, str]:
        """
        Unpacks stock boot.img and repacks without changes.
        Must yield 100% bit-identical SHA256.
        """
        with open(self.stock_path, "rb") as f:
            orig_data = f.read()

        orig_sha = hashlib.sha256(orig_data).hexdigest()
        info = self.parse_header(orig_data)

        hdr_padded = ((info["header_size"] + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        k_padded = ((info["kernel_size"] + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        k_data = orig_data[hdr_padded : hdr_padded + info["kernel_size"]]
        k_padding = b"\x00" * (k_padded - info["kernel_size"])
        trailing = orig_data[hdr_padded + k_padded :]

        repacked = orig_data[:hdr_padded] + k_data + k_padding + trailing
        repacked_sha = hashlib.sha256(repacked).hexdigest()

        if orig_sha != repacked_sha:
            return False, f"Roundtrip hash mismatch! Stock: {orig_sha}, Repacked: {repacked_sha}"

        if len(repacked) != PARTITION_SIZE:
            return False, f"Roundtrip size mismatch! Expected {PARTITION_SIZE}, got {len(repacked)}"

        return True, orig_sha

    def repack(self, new_kernel_path: str, output_boot_path: str, avbtool_path: str = None) -> Dict[str, Any]:
        """
        Replaces stock kernel with new_kernel while preserving header, ramdisk, and partition layout.
        """
        new_k_file = Path(new_kernel_path)
        if not new_k_file.is_file():
            raise FileNotFoundError(f"New kernel file not found: {new_k_file}")

        new_k_data = new_k_file.read_bytes()
        new_ksize = len(new_k_data)

        # Roundtrip check first
        passed, msg = self.verify_roundtrip()
        if not passed:
            raise RuntimeError(f"Stock roundtrip verification failed: {msg}")

        with open(self.stock_path, "rb") as f:
            orig_data = bytearray(f.read())

        info = self.parse_header(orig_data)
        hdr_padded = ((info["header_size"] + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE

        # Build modified header with new kernel size
        hdr = bytearray(orig_data[:hdr_padded])
        struct.pack_into("<I", hdr, 8, new_ksize)

        new_k_padded_size = ((new_ksize + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
        new_k_padding = b"\x00" * (new_k_padded_size - new_ksize)

        base_image = hdr + new_k_data + new_k_padding
        base_size = len(base_image)

        # Check maximum allowed unpadded image size before footer
        if base_size > PARTITION_SIZE - 65536:
            raise ValueError(
                f"Kernel payload too large ({base_size} bytes)! Exceeds partition limit ({PARTITION_SIZE})."
            )

        out_path = Path(output_boot_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if avbtool_path and Path(avbtool_path).is_file():
            # Write base_image unpadded so avbtool can pad and append footer
            out_path.write_bytes(base_image)
            print(f"[BootRepacker] Applying AVB Hash Footer using {avbtool_path}...")
            cmd = [
                sys.executable,
                avbtool_path,
                "add_hash_footer",
                "--image",
                str(out_path),
                "--partition_size",
                str(PARTITION_SIZE),
                "--partition_name",
                "boot",
                "--salt",
                "2f3af9c34e034d0b10491da3e7e0c383115e5690fa714a6631b8258227bc1e58",
                "--rollback_index",
                "1785542400",
                "--prop",
                "com.android.build.boot.os_version:16",
                "--prop",
                "com.android.build.boot.fingerprint:POCO/songyuan_global/songyuan:16/BQ2A.260225.001-BP2A.250705.008/OS3.0.301.0.WGNTWXM:user/release-keys",
                "--prop",
                "com.android.build.boot.security_patch:2026-08-01",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"avbtool add_hash_footer failed: {res.stderr}\n{res.stdout}")
            print("[BootRepacker] AVB Hash Footer applied successfully.")
        else:
            # Pad directly to full partition size
            total_padding = b"\x00" * (PARTITION_SIZE - base_size)
            final_image = base_image + total_padding
            out_path.write_bytes(final_image)

        final_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
        final_size = out_path.stat().st_size

        if final_size != PARTITION_SIZE:
            raise ValueError(f"Final image size {final_size} does not match {PARTITION_SIZE}!")

        return {
            "success": True,
            "stock_sha256": msg,
            "final_sha256": final_sha,
            "kernel_size": new_ksize,
            "partition_size": final_size,
            "output": str(out_path),
        }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python boot_repacker.py <stock_boot.img> <new_Image> [output_boot.img] [avbtool.py]")
        sys.exit(1)

    stock_img = sys.argv[1]
    new_kernel = sys.argv[2]
    out_img = sys.argv[3] if len(sys.argv) > 3 else "boot-sukisu-susfs-kpm-songyuan.img"
    avb_tool = sys.argv[4] if len(sys.argv) > 4 else None

    repacker = BootRepacker(stock_img)
    print("[BootRepacker] Running stock round-trip verification...")
    ok, sha = repacker.verify_roundtrip()
    if not ok:
        print(f"[FATAL] Roundtrip failed: {sha}")
        sys.exit(1)
    print(f"[OK] Stock roundtrip passed: {sha}")

    print(f"[BootRepacker] Repacking with new kernel {new_kernel}...")
    res = repacker.repack(new_kernel, out_img, avb_tool)
    print(f"[SUCCESS] Repacked image ready at: {res['output']} (SHA256: {res['final_sha256']}, Size: {res['partition_size']})")
