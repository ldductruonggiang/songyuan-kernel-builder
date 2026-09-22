"""
Device Detector Module
Handles device inspection via ADB and Fastboot, extracts kernel release, KMI, page size,
and verified boot status without making destructive changes.
"""

import subprocess
import re
from typing import Dict, Any, Optional


class DeviceDetector:
    def __init__(self, adb_path: str = "adb", fastboot_path: str = "fastboot"):
        self.adb = adb_path
        self.fastboot = fastboot_path

    def run_cmd(self, args: list) -> str:
        try:
            res = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            return res.stdout.strip()
        except Exception as e:
            return ""

    def get_adb_devices(self) -> list:
        out = self.run_cmd([self.adb, "devices"])
        devices = []
        for line in out.splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def get_fastboot_devices(self) -> list:
        out = self.run_cmd([self.fastboot, "devices"])
        devices = []
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] in ("fastboot", "rescue"):
                devices.append(parts[0])
        return devices

    def detect_device_adb(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            "online": False,
            "mode": "none",
            "serial": "",
            "manufacturer": "",
            "model": "",
            "device": "",
            "android_version": "",
            "sdk": "",
            "kernel_release": "",
            "kernel_base": "",
            "kmi": "",
            "kmi_generation": "",
            "page_size": 0,
            "current_slot": "",
            "verified_boot_state": "",
            "device_state": "",
            "is_songyuan": False,
        }

        devices = self.get_adb_devices()
        if not devices:
            # Check fastboot
            fb_devices = self.get_fastboot_devices()
            if fb_devices:
                info["online"] = True
                info["mode"] = "fastboot"
                info["serial"] = fb_devices[0]
                info["current_slot"] = self.run_cmd(
                    [self.fastboot, "getvar", "current-slot"]
                ).replace("current-slot:", "").strip()
            return info

        serial = devices[0]
        info["online"] = True
        info["mode"] = "adb"
        info["serial"] = serial

        info["manufacturer"] = self.run_cmd([self.adb, "shell", "getprop", "ro.product.manufacturer"])
        info["model"] = self.run_cmd([self.adb, "shell", "getprop", "ro.product.model"])
        info["device"] = self.run_cmd([self.adb, "shell", "getprop", "ro.product.device"])
        info["android_version"] = self.run_cmd([self.adb, "shell", "getprop", "ro.build.version.release"])
        info["sdk"] = self.run_cmd([self.adb, "shell", "getprop", "ro.build.version.sdk"])

        # Kernel release & parsing
        kernel_rel = self.run_cmd([self.adb, "shell", "uname", "-r"])
        info["kernel_release"] = kernel_rel
        parsed = self.parse_kernel_release(kernel_rel)
        info.update(parsed)

        # Page Size
        page_size_str = self.run_cmd([self.adb, "shell", "getprop", "ro.boot.hardware.cpu.pagesize"])
        if not page_size_str:
            page_size_str = self.run_cmd([self.adb, "shell", "getconf", "PAGE_SIZE"])
        try:
            info["page_size"] = int(page_size_str)
        except ValueError:
            info["page_size"] = 4096 if "-4k" in kernel_rel else 0

        # Boot & Slot status
        slot = self.run_cmd([self.adb, "shell", "getprop", "ro.boot.slot_suffix"]).replace("_", "")
        info["current_slot"] = slot if slot else "a"
        info["verified_boot_state"] = self.run_cmd([self.adb, "shell", "getprop", "ro.boot.verifiedbootstate"])
        info["device_state"] = self.run_cmd([self.adb, "shell", "getprop", "ro.boot.vbmeta.device_state"])

        if info["device"] == "songyuan" or info["model"] in ("26077PC53G", "Redmi K100 Pro Max"):
            info["is_songyuan"] = True

        return info

    @staticmethod
    def parse_kernel_release(release: str) -> Dict[str, str]:
        """
        Parses kernel release strings such as:
        6.12.69-android16-6-g0d80ee00f747-ab15461283-4k
        """
        res = {
            "kernel_base": "",
            "kmi": "",
            "kmi_generation": "",
            "android_branch": "",
            "commit_hash": "",
        }
        if not release:
            return res

        # Regex for standard AOSP GKI version format
        pattern = r"^(\d+\.\d+\.\d+)-(android\d+)-(\d+)-(g[0-9a-fA-F]+)"
        match = re.search(pattern, release)
        if match:
            res["kernel_base"] = ".".join(match.group(1).split(".")[:2])
            res["android_branch"] = match.group(2)
            res["kmi_generation"] = f"{match.group(2)}-{match.group(3)}"
            res["kmi"] = f"{match.group(2)}-{res['kernel_base']}"
            res["commit_hash"] = match.group(4)
        else:
            parts = release.split("-")
            if len(parts) >= 1:
                res["kernel_base"] = ".".join(parts[0].split(".")[:2])
            if len(parts) >= 2:
                res["android_branch"] = parts[1]
                res["kmi"] = f"{parts[1]}-{res['kernel_base']}"

        return res
