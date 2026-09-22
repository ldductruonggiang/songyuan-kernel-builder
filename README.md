# songyuan-sukisu-builder: SukiSU Ultra Built-in Kernel Builder & Safe Flasher

> **Target Device**: Xiaomi Redmi K100 Pro Max (`songyuan`)  
> **Platform**: Snapdragon 8 Elite Gen 5 (SM8750) / aarch64  
> **Firmware**: HyperOS 3 / Android 16 (SDK 36)  
> **Kernel Base**: Linux 6.12.x GKI (`android16-6.12`, 4KB Page Size)  
> **Boot Structure**: Android Boot Header v4 (`boot.img` contains kernel `Image`, `init_boot.img` contains generic ramdisk)

---

## 1. Giới thiệu & Mục tiêu (Overview)

`songyuan-sukisu-builder` là bộ công cụ chuyên dụng chạy trên Windows (GUI PySide6 hiện đại) kết hợp backend build WSL2 / Linux. Tool giải quyết bài toán:

1. **Thay thế SukiSU Ultra LKM bằng Kernel Built-in**:
   - Tích hợp trực tiếp mã nguồn **SukiSU Ultra** (`builtin` mode) vào Linux Kernel 6.12.
   - Tích hợp driver ẩn root **SUSFS** (Kernel-side Susfs driver).
   - Kích hoạt và khóa cứng **Kernel Patch Module (KPM)** (`CONFIG_KPM=y`).
   - Loại bỏ hoàn toàn dấu vết tải module động (`.ko` in ramdisk / vendor_dlkm), ngăn chặn triệt để các kỹ thuật quét module của DroidGuard, Play Integrity, và ngân hàng.

2. **Quy trình An toàn Tuyệt đối (Fail-Closed Flashing Policy)**:
   - Tự động nhận diện thiết bị, KMI, Page size (4K), Boot Header v4 và Active Slot (`_a`/`_b`).
   - Kiểm tra tương thích 5 cấp độ (5-Tier Source Hierarchy).
   - Tự động khóa nút Flash nếu kernel source là `PARTIAL_SOURCE` hoặc `UNKNOWN`.
   - Bảo vệ tuyệt đối phân vùng hệ thống quan trọng: **KHÔNG BAO GIỜ** can thiệp hay xóa `userdata`, `persist`, `modem`, `efs`, `metadata`, `vbmeta`.
   - Bắt buộc Backup Stock Boot và đối soát SHA256 trước khi flash.
   - Giám sát khởi động (Boot Verification Watchdog 180s) và Cứu hộ khẩn cấp 1-click (Emergency One-Click Rollback).

---

## 2. Cấu trúc Dự án (Architecture)

```text
songyuan-sukisu-builder/
├── main.py                        # Entrypoint: khởi chạy GUI PySide6 hoặc CLI diagnostics
├── requirements.txt               # Danh sách thư viện phụ thuộc (PySide6, pytest)
├── README.md                      # Tài liệu kỹ thuật chi tiết
├── src/
│   ├── __init__.py
│   ├── config.py                  # Cấu hình phần cứng, TargetDeviceSpecs & RESTRICTED_PARTITIONS
│   ├── device_detector.py         # Nhận diện ADB / Fastboot, bóc tách kernel release, KMI, slot
│   ├── source_detector.py         # 5-Tier search hierarchy & cơ chế Fail-Closed
│   ├── sukisu_integrator.py       # Tích hợp setup.sh upstream, SUSFS branch, CONFIG_KPM=y
│   ├── boot_analyzer.py           # Parser Header v3/v4, trích xuất kernel Image & repacker
│   ├── abi_validator.py           # Đối soát ABI stock vs built, xuất FLASH SAFETY REPORT
│   ├── flasher.py                 # Flash an toàn, slot-aware, watchdog 180s, emergency restore
│   └── gui.py                     # Giao diện đồ họa PySide6 với 7 Tabs chức năng
├── profiles/
│   └── module_profiles.json       # Profile module mẫu (Play Integrity, Banking, Gaming)
├── scripts/
│   ├── build_kernel.sh            # Script build kernel hoàn chỉnh trong môi trường WSL2/Linux
│   └── reproduce.sh               # Script kiểm tra tính tái lập (reproducible build) qua SHA256
└── tests/
    ├── __init__.py
    └── test_parsers.py            # 12 Unit Tests kiểm thử parser, unpack/repack boot v4, safety gate
```

---

## 3. Các Tab Chức Năng trong GUI (PySide6 Dashboard)

1. **`DEVICE` (Nhận diện thiết bị)**:
   - Tự động quét thông số qua ADB / Fastboot: Codename (`songyuan`), Model (`26077PC53G`), Android 16, Kernel Release (`6.12.69-android16-6...-4k`), KMI (`android16-6.12`), Page size (`4096`), Active slot (`_a`/`_b`), Trạng thái bootloader (`orange/unlocked`).
   - Nút Reboot sang Fastboot / System.
2. **`SOURCE` (Quản lý nguồn & Safety Gate)**:
   - Hiển thị bảng tra cứu 5 cấp độ mã nguồn (Tier 1: MiCode Official, Tier 2: MiCode GitHub, Tier 3: AOSP ACK 6.12, Tier 4: Qualcomm SoC, Tier 5: Community).
   - Banner cảnh báo Fail-Closed: Khóa tự động khi Xiaomi chưa phát hành device source chính thức cho `songyuan`.
   - Công tắc mở khóa "Developer / Research Override" cho mục đích thử nghiệm AOSP ACK.
3. **`BUILD` (Cấu hình & Biên dịch Kernel)**:
   - Chọn Hook Method: `KPROBES` (khuyên dùng), `TRACEPOINT`, `MANUAL`.
   - Chọn nhánh SUSFS: `Auto Stable`, `susfs-main`, `Versioned`, `susfs-test`, `Disabled`.
   - Checkbox kích hoạt KPM: `CONFIG_KPM=y` (bắt buộc).
   - Tạo preview script tích hợp và gọi trực tiếp script WSL2 biên dịch.
4. **`FLASH` (Flash an toàn & Giám sát)**:
   - Hiển thị **FLASH SAFETY REPORT**: đối soát Device, Arch, Kernel Base, KMI, Page Size, Header Version, Vendor Module ABI.
   - Chọn file `patched_boot.img` và hiển thị phân vùng đích an toàn (`boot_a` hoặc `boot_b`).
   - **6 Cổng kiểm soát bắt buộc (6 Checkboxes)** trước khi nút Flash mở:
     1. Đã sao lưu stock `boot.img` và kiểm tra SHA256.
     2. Xác nhận codename là `songyuan` (Snapdragon 8 Elite Gen 5).
     3. Xác nhận ROM HyperOS 3 (Android 16).
     4. Xác nhận KMI khớp `android16-6.12`.
     5. Xác nhận Page size là 4096 (4K).
     6. Đã hiểu rủi ro bootloop và có sẵn fastboot để cứu hộ.
   - Tiến trình flash kèm đếm ngược Watchdog 180s để xác nhận thiết bị khởi động thành công.
5. **`MODULES` (Cấu hình Module & Giải pháp Play Integrity)**:
   - Danh sách cấu hình mẫu cho HyperOS 3:
     - **Tricky Store**: Chế độ Leaf Hack với chứng chỉ Google Droid CA3 (đạt `DEVICE_INTEGRITY`).
     - **SUSFS Daemon/Tools**: Che giấu `/proc/bootconfig` (tránh lộ trạng thái `orange/unlocked`).
     - **ReZygisk + Zygisk NoHello**: Zygisk tương thích Android 16, ẩn socket IPC.
     - **Vô hiệu hóa Play Integrity Fix (PIF)**: Tránh crash `arm64-v8a.so` trong GMS unstable gây `BASIC=FAIL`.
6. **`BACKUP` (Sao lưu & Cứu hộ khẩn cấp)**:
   - Tạo bản sao lưu stock boot có gắn timestamp (`stock_boot_backup_YYYYMMDD_HHMMSS.img`).
   - Kiểm tra tính toàn vẹn Header v4 và SHA256 của file ảnh boot.
   - **EMERGENCY ONE-CLICK RESTORE**: Khôi phục ảnh boot gốc về phân vùng active slot và khởi động lại ngay khi gặp sự cố bootloop.
7. **`LOGS` (Nhật ký thời gian thực)**:
   - Ghi nhận chi tiết toàn bộ lệnh Fastboot, ADB, trạng thái biên dịch và lỗi.
   - Hỗ trợ Copy, Export ra file `.txt`, và lọc theo cấp độ.

---

## 4. Hướng dẫn Sử dụng (Quick Start)

### Yêu cầu hệ thống:
- Windows 10/11 64-bit.
- Python 3.10+ (đã cài `PySide6`).
- ADB và Fastboot đã thêm vào biến môi trường `PATH`.
- WSL2 (Ubuntu) nếu muốn biên dịch trực tiếp trên máy.

### Khởi chạy Giao diện Đồ họa (GUI):
```powershell
cd songyuan-sukisu-builder
python main.py
```

### Chạy chế độ Kiểm tra Dòng lệnh (CLI Diagnostics):
```powershell
# Quét thông tin thiết bị đang cắm
python main.py --detect

# Kiểm tra trạng thái nguồn kernel & đánh giá an toàn
python main.py --check-source

# Kiểm tra tính toàn vẹn của một file boot.img (Header v3/v4)
python main.py --verify-boot c:\Users\admin\Desktop\rooot\init_boot.img
```

### Chạy Bộ Kiểm Thử (Unit Tests):
```powershell
python -m unittest discover tests
```

---

## 5. Giải thích Kỹ thuật: Play Integrity trên Android 16 & HyperOS 3

| Tiêu chí | Trạng thái | Nguyên nhân kỹ thuật & Giải pháp |
| :--- | :---: | :--- |
| **BASIC INTEGRITY** | **FAIL -> PASS** | **Nguyên nhân FAIL ban đầu**: Module PIF inject file thư viện Zygisk `arm64-v8a.so` trực tiếp vào tiến trình `com.google.android.gms.unstable` gây crash bộ nhớ trên Android 16; đồng thời DroidGuard đọc trực tiếp `/proc/bootconfig` thấy `verifiedbootstate = "orange"`.<br>**Giải pháp**: Tắt module PIF, sử dụng kernel tích hợp SUSFS để giả lập `/proc/bootconfig`. |
| **DEVICE INTEGRITY** | **PASS** | Hoạt động thành công nhờ Tricky Store chạy ở chế độ **Leaf Hack** với chứng chỉ hợp lệ **Google Droid CA3** (hạn dùng đến 27-09-2026). |
| **STRONG INTEGRITY** | **FAIL** | Đòi hỏi phần cứng Keymaster/TEE xác thực chữ ký khóa bảo mật (Keybox) thông qua danh sách thu hồi thời gian thực của Google (Google Cloud CRL). Mọi Keybox công khai trên mạng đều đã bị thu hồi trong danh sách CRL. **Chỉ có thể đạt được nếu sở hữu Private Unrevoked Keybox cá nhân.** |

---

## 6. Chính sách Bảo vệ Dữ liệu & An toàn Phần cứng

- **Danh sách phân vùng cấm (Blacklisted Partitions)**:
  `userdata`, `persist`, `modem`, `modemst1`, `modemst2`, `fsg`, `fsc`, `efs`, `frp`, `metadata`, `vbmeta`, `vbmeta_system`, `vbmeta_vendor`, `secdata`, `devinfo`.
- **Boot Header v4 Architecture**:
  Trên Xiaomi HyperOS 3 (Snapdragon 8 Elite), `boot.img` chỉ chứa Kernel Image (ramdisk size = 0). Ramdisk gốc nằm hoàn toàn ở `init_boot.img`. Khi can thiệp SukiSU Ultra built-in, tool đóng gói lại kernel `Image` vào đúng `boot.img`, bảo lưu header offset và padding 4096 bytes chuẩn xác.
- **Fail-Closed Gate**:
  Nếu nguồn kernel không có đầy đủ cây mã nguồn thiết bị chính thức từ Xiaomi (trạng thái `PARTIAL_SOURCE`), hệ thống sẽ từ chối tự động nạp để ngăn ngừa rủi ro mất cảm ứng hoặc màn hình đen do sai lệch driver ngoài cây (`vendor_dlkm`).
