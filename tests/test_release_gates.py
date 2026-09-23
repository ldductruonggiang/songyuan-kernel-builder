import tempfile
import unittest
from pathlib import Path

from tools.abi_crc_validator import EXPECTED_RELEASE, validate
from tools.kernel_release import read_release
from tools.stock_config_gate import check


class ReleaseGateTests(unittest.TestCase):
    def test_embedded_release_is_read_from_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "Image"
            image.write_bytes(b"\0Linux version 6.12.69-4k-dirty \0")
            self.assertEqual(read_release(image), "6.12.69-4k-dirty")

    def test_abi_gate_rejects_missing_symbol_and_near_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Module.symvers").write_text("0x12345678\tfoo\tvmlinux\tEXPORT_SYMBOL\t\n")
            (root / "reference.json").write_text(
                '{"foo": {"crc": "0x12345678"}, "bar": {"crc": "0x87654321"}}'
            )
            result = validate(
                str(root / "Module.symvers"),
                str(root / "reference.json"),
                EXPECTED_RELEASE,
                str(root / "report.txt"),
            )
            self.assertFalse(result["abi_compatible"])
            result = validate(
                str(root / "Module.symvers"),
                str(root / "reference.json"),
                EXPECTED_RELEASE + "-custom",
                str(root / "report.txt"),
            )
            self.assertFalse(result["release_match"])

    def test_stock_config_gate_rejects_disabled_rust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stock = root / "stock.config"
            built = root / "built.config"
            values = "\n".join(f"{key}=y" for key in (
                "CONFIG_ARM64_4K_PAGES", "CONFIG_MODVERSIONS", "CONFIG_RUST",
                "CONFIG_TRIM_UNUSED_KSYMS", "CONFIG_MODULE_SIG_PROTECT",
                "CONFIG_SECURITY_SELINUX",
            ))
            stock.write_text(values)
            built.write_text(values.replace("CONFIG_RUST=y", "# CONFIG_RUST is not set"))
            self.assertIn("CONFIG_RUST", "\n".join(check(stock, built)))

    def test_abi_gate_rejects_malformed_stock_crc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Module.symvers").write_text("0x12345678\tfoo\tvmlinux\tEXPORT_SYMBOL\t\n")
            (root / "reference.json").write_text(
                '{"foo": {"crc": "0x1234567890abcdef"}}'
            )
            result = validate(
                str(root / "Module.symvers"),
                str(root / "reference.json"),
                EXPECTED_RELEASE,
                str(root / "report.txt"),
            )
            self.assertEqual(result["invalid_reference"], 1)
            self.assertFalse(result["abi_compatible"])


if __name__ == "__main__":
    unittest.main()
