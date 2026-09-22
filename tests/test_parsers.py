"""
Unit Tests for songyuan-sukisu-builder Parsers, Analyzers, and Safety Gates
"""

import unittest
import struct
import tempfile
import shutil
from pathlib import Path

from src.config import RESTRICTED_PARTITIONS, SourceStatus
from src.device_detector import DeviceDetector
from src.boot_analyzer import BootAnalyzer, BOOT_MAGIC
from src.abi_validator import AbiValidator
from src.source_detector import SourceDetector
from src.flasher import SafeFlasher


class TestKernelParsers(unittest.TestCase):
    def test_parse_kernel_release_songyuan(self):
        rel = "6.12.69-android16-6-g0d80ee00f747-ab15461283-4k"
        parsed = DeviceDetector.parse_kernel_release(rel)
        self.assertEqual(parsed["kernel_base"], "6.12")
        self.assertEqual(parsed["android_branch"], "android16")
        self.assertEqual(parsed["kmi_generation"], "android16-6")
        self.assertEqual(parsed["kmi"], "android16-6.12")
        self.assertEqual(parsed["commit_hash"], "g0d80ee00f747")

    def test_parse_kernel_release_generic(self):
        rel = "6.6.21-android15-2-g12345678"
        parsed = DeviceDetector.parse_kernel_release(rel)
        self.assertEqual(parsed["kernel_base"], "6.6")
        self.assertEqual(parsed["android_branch"], "android15")
        self.assertEqual(parsed["kmi"], "android15-6.6")

    def test_parse_kernel_release_empty(self):
        parsed = DeviceDetector.parse_kernel_release("")
        self.assertEqual(parsed["kernel_base"], "")
        self.assertEqual(parsed["kmi"], "")


class TestBootAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.boot_path = Path(self.test_dir) / "synthetic_boot.img"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_synthetic_boot_v4(self, kernel_bytes: bytes, ramdisk_bytes: bytes) -> Path:
        """
        Creates a synthetic Android Boot Header v4 binary according to AOSP specification:
        boot_img_hdr_v4:
        uint8_t magic[8]
        uint32_t kernel_size
        uint32_t ramdisk_size
        uint32_t os_version
        uint32_t header_size
        uint32_t reserved[4]
        uint32_t header_version (=4)
        uint32_t signature_size
        """
        header_size = 4096
        page_size = 4096
        kernel_size = len(kernel_bytes)
        ramdisk_size = len(ramdisk_bytes)
        os_version = (16 << 25) | (2026 << 4) | 8  # Android 16, Aug 2026

        # Construct header
        header = bytearray(header_size)
        header[0:8] = BOOT_MAGIC
        struct.pack_into("<I", header, 8, kernel_size)
        struct.pack_into("<I", header, 12, ramdisk_size)
        struct.pack_into("<I", header, 16, os_version)
        struct.pack_into("<I", header, 20, header_size)
        # header_version at offset 40 (after magic 8 + 4x uint32_t + 4x uint32_t reserved)
        # offset 8 + 16 (4 ints) + 16 (4 reserved ints) = 40
        struct.pack_into("<I", header, 40, 4)

        # Pad kernel to 4096 boundary
        kernel_padded_len = ((kernel_size + page_size - 1) // page_size) * page_size
        padded_kernel = kernel_bytes + b"\x00" * (kernel_padded_len - kernel_size)

        # Write out
        with open(self.boot_path, "wb") as f:
            f.write(header)
            f.write(padded_kernel)
            f.write(ramdisk_bytes)

        return self.boot_path

    def test_boot_analyzer_v4_parsing(self):
        dummy_kernel = b"K100_PRO_MAX_KERNEL_PAYLOAD" * 10
        dummy_ramdisk = b"RAMDISK_DATA" * 5
        self._create_synthetic_boot_v4(dummy_kernel, dummy_ramdisk)

        analyzer = BootAnalyzer(str(self.boot_path))
        info = analyzer.analyze()

        self.assertTrue(info["valid"])
        self.assertEqual(info["header_version"], 4)
        self.assertEqual(info["kernel_size"], len(dummy_kernel))
        self.assertEqual(info["ramdisk_size"], len(dummy_ramdisk))
        self.assertTrue(len(info["sha256"]) == 64)

    def test_boot_kernel_extraction_and_repack(self):
        dummy_kernel = b"ORIGINAL_KERNEL_BYTES" * 30
        dummy_ramdisk = b"RAMDISK_PAYLOAD" * 10
        self._create_synthetic_boot_v4(dummy_kernel, dummy_ramdisk)

        analyzer = BootAnalyzer(str(self.boot_path))

        # 1. Extract Kernel
        extracted_kernel = Path(self.test_dir) / "extracted_Image"
        success = analyzer.extract_kernel(str(extracted_kernel))
        self.assertTrue(success)
        self.assertEqual(extracted_kernel.read_bytes(), dummy_kernel)

        # 2. Repack with new kernel
        new_kernel_bytes = b"NEW_SUKISU_PATCHED_KERNEL" * 40
        new_kernel_path = Path(self.test_dir) / "new_Image"
        new_kernel_path.write_bytes(new_kernel_bytes)

        repacked_boot_path = Path(self.test_dir) / "repacked_boot.img"
        repack_success = analyzer.repack_kernel(str(new_kernel_path), str(repacked_boot_path))
        self.assertTrue(repack_success)

        # 3. Analyze repacked image
        repack_analyzer = BootAnalyzer(str(repacked_boot_path))
        repack_info = repack_analyzer.analyze()
        self.assertTrue(repack_info["valid"])
        self.assertEqual(repack_info["header_version"], 4)
        self.assertEqual(repack_info["kernel_size"], len(new_kernel_bytes))

        # 4. Extract from repacked image and verify exact byte match
        re_extracted = Path(self.test_dir) / "re_extracted_Image"
        repack_analyzer.extract_kernel(str(re_extracted))
        self.assertEqual(re_extracted.read_bytes(), new_kernel_bytes)

    def test_invalid_magic(self):
        corrupt_file = Path(self.test_dir) / "corrupt.img"
        corrupt_file.write_bytes(b"NOT_ANDROID_MAGIC_HEADER_DATA")
        analyzer = BootAnalyzer(str(corrupt_file))
        info = analyzer.analyze()
        self.assertFalse(info["valid"])
        self.assertIn("Invalid magic", info["error"])


class TestAbiValidator(unittest.TestCase):
    def test_perfect_match(self):
        stock = {
            "device": "songyuan",
            "is_songyuan": True,
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 4096,
            "boot_header_version": 4,
        }
        built = {
            "arch": "arm64",
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 4096,
            "boot_header_version": 4,
            "has_exact_device_source": True,
        }
        validator = AbiValidator(stock, built)
        res = validator.evaluate_safety()
        self.assertTrue(res["safe"])
        self.assertEqual(res["overall"], "SAFE TO TEST")

    def test_partial_source_fails_closed(self):
        stock = {
            "device": "songyuan",
            "is_songyuan": True,
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 4096,
            "boot_header_version": 4,
        }
        built = {
            "arch": "arm64",
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 4096,
            "boot_header_version": 4,
            "has_exact_device_source": False,  # Xiaomi in-tree unreleased
        }
        validator = AbiValidator(stock, built)
        res = validator.evaluate_safety()
        self.assertFalse(res["safe"])
        self.assertIn("VENDOR ABI UNKNOWN", res["overall"])

    def test_page_size_mismatch_fails(self):
        stock = {
            "device": "songyuan",
            "is_songyuan": True,
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 4096,
            "boot_header_version": 4,
        }
        built = {
            "arch": "arm64",
            "kernel_base": "6.12",
            "kmi": "android16-6.12",
            "page_size": 16384,  # Mismatch: 16k built for 4k device
            "boot_header_version": 4,
            "has_exact_device_source": True,
        }
        validator = AbiValidator(stock, built)
        res = validator.evaluate_safety()
        self.assertFalse(res["safe"])
        self.assertIn("CRITICAL FAILURE", res["overall"])


class TestSafetyAndPartitions(unittest.TestCase):
    def test_restricted_partitions(self):
        self.assertIn("userdata", RESTRICTED_PARTITIONS)
        self.assertIn("persist", RESTRICTED_PARTITIONS)
        self.assertIn("modem", RESTRICTED_PARTITIONS)
        self.assertIn("efs", RESTRICTED_PARTITIONS)
        self.assertIn("metadata", RESTRICTED_PARTITIONS)
        self.assertIn("vbmeta", RESTRICTED_PARTITIONS)

    def test_flasher_blocks_missing_confirmation(self):
        flasher = SafeFlasher()
        incomplete_confirm = {
            "stock_backed_up": True,
            "codename_verified": True,
            "rom_version_verified": True,
            # Missing 3 checks
        }
        res = flasher.execute_flash("nonexistent.img", incomplete_confirm)
        self.assertFalse(res["success"])
        self.assertIn("Safety gate violation", res["error"])

    def test_source_detector_hierarchy(self):
        detector = SourceDetector()
        res = detector.determine_source_status()
        self.assertEqual(res["status"], SourceStatus.PARTIAL_SOURCE)
        self.assertFalse(res["can_flash"])
        self.assertFalse(res["can_auto_build"])
        self.assertEqual(len(res["candidates"]), 5)


if __name__ == "__main__":
    unittest.main()
