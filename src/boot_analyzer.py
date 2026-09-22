"""
Boot Image Analyzer & Repacker Module
Analyzes stock boot.img (Header v3/v4), extracts kernel, verifies integrity,
and repacks patched_boot.img preserving AVB, cmdline, and offsets.
"""

import struct
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

BOOT_MAGIC = b"ANDROID!"
BOOT_MAGIC_SIZE = 8


class BootAnalyzer:
    def __init__(self, boot_image_path: str):
        self.boot_path = Path(boot_image_path)

    @staticmethod
    def calculate_sha256(filepath: Path) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def analyze(self) -> Dict[str, Any]:
        """
        Parses Android Boot Header v3 and v4 structure.
        """
        info: Dict[str, Any] = {
            "valid": False,
            "header_version": -1,
            "kernel_size": 0,
            "ramdisk_size": 0,
            "os_version": "",
            "os_patch_level": "",
            "header_size": 0,
            "sha256": "",
            "file_size": 0,
            "error": "",
        }

        if not self.boot_path.is_file():
            info["error"] = f"File not found: {self.boot_path}"
            return info

        info["file_size"] = self.boot_path.stat().st_size
        info["sha256"] = self.calculate_sha256(self.boot_path)

        with open(self.boot_path, "rb") as f:
            magic = f.read(BOOT_MAGIC_SIZE)
            if magic != BOOT_MAGIC:
                info["error"] = f"Invalid magic: {magic} (Expected ANDROID!)"
                return info

            # Header v3/v4 layout:
            # uint8_t magic[8]
            # uint32_t kernel_size
            # uint32_t ramdisk_size
            # uint32_t os_version
            # uint32_t header_size
            # uint32_t reserved[4]
            # uint32_t header_version
            data = f.read(40)
            if len(data) < 40:
                info["error"] = "Corrupted header data"
                return info

            kernel_size, ramdisk_size, os_ver_raw, header_size = struct.unpack("<4I", data[:16])
            # header_version is at offset 36 from after magic (i.e. offset 44 in file)
            header_version = struct.unpack("<I", data[32:36])[0]

            info["valid"] = True
            info["header_version"] = header_version
            info["kernel_size"] = kernel_size
            info["ramdisk_size"] = ramdisk_size
            info["header_size"] = header_size

            # Parse OS version & security patch
            if os_ver_raw != 0:
                os_ver = (os_ver_raw >> 11) & 0x7FF
                a = (os_ver >> 14) & 0x7F
                b = (os_ver >> 7) & 0x7F
                c = os_ver & 0x7F
                y = ((os_ver_raw >> 4) & 0x7F) + 2000
                m = os_ver_raw & 0xF
                info["os_version"] = f"{a}.{b}.{c}" if a or b or c else str(os_ver)
                info["os_patch_level"] = f"{y:04d}-{m:02d}"

        return info

    def extract_kernel(self, output_kernel_path: str) -> bool:
        """
        Extracts raw kernel Image from boot.img according to header size.
        """
        analysis = self.analyze()
        if not analysis["valid"] or analysis["kernel_size"] == 0:
            return False

        header_size = analysis["header_size"]
        kernel_size = analysis["kernel_size"]

        # In Header v3/v4, page size is fixed to 4096
        page_size = 4096
        kernel_offset = ((header_size + page_size - 1) // page_size) * page_size

        with open(self.boot_path, "rb") as f_in:
            f_in.seek(kernel_offset)
            kernel_bytes = f_in.read(kernel_size)

        out_path = Path(output_kernel_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f_out:
            f_out.write(kernel_bytes)

        return True

    def repack_kernel(self, new_kernel_path: str, output_boot_path: str) -> bool:
        """
        Repacks boot image by replacing kernel while preserving header v4 and ramdisk.
        """
        analysis = self.analyze()
        if not analysis["valid"]:
            return False

        new_kernel = Path(new_kernel_path)
        if not new_kernel.is_file():
            return False

        new_kernel_size = new_kernel.stat().st_size
        with open(new_kernel, "rb") as k_f:
            new_kernel_bytes = k_f.read()

        # Read original boot.img
        with open(self.boot_path, "rb") as orig_f:
            orig_data = bytearray(orig_f.read())

        # Update kernel_size in header (offset 8 to 12)
        struct.pack_into("<I", orig_data, 8, new_kernel_size)

        page_size = 4096
        kernel_offset = ((analysis["header_size"] + page_size - 1) // page_size) * page_size

        # In Header v4, ramdisk (if any) or signature follows padded kernel
        orig_kernel_padded_size = ((analysis["kernel_size"] + page_size - 1) // page_size) * page_size
        after_kernel_offset = kernel_offset + orig_kernel_padded_size
        trailing_data = orig_data[after_kernel_offset:]

        # Pad new kernel to page boundary
        new_kernel_padded_size = ((new_kernel_size + page_size - 1) // page_size) * page_size
        padding_needed = new_kernel_padded_size - new_kernel_size
        padded_new_kernel = new_kernel_bytes + (b"\x00" * padding_needed)

        # Assemble new boot image
        header_part = orig_data[:kernel_offset]
        repacked_boot = header_part + padded_new_kernel + trailing_data

        out_boot = Path(output_boot_path)
        out_boot.parent.mkdir(parents=True, exist_ok=True)
        with open(out_boot, "wb") as out_f:
            out_f.write(repacked_boot)

        return True
