@echo off
setlocal enabledelayedexpansion
title Khôi Phục Stock Boot - Redmi K100 Pro Max (songyuan)
color 0B

echo ====================================================================
echo   KHOI PHUC STOCK BOOT GOC - REDMI K100 PRO MAX (songyuan)
echo   ROM: OS3.0.301.0.WGNTWXM (Android 16 / HyperOS 3)
echo ====================================================================
echo.
echo [AN TOAN] Script nay TUYET DOI KHONG xoa du lieu (NO WIPE).
echo [AN TOAN] Script nay TUYET DOI KHONG khoa lai Bootloader (NO RELOCK).
echo.
echo Vui long ket noi dien thoai o che do FASTBOOT...
echo.

fastboot devices >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay thiet bi o che do Fastboot!
    echo Hay giu phim Nguon + Giam Am Luong de vao lai Fastboot roi chay lai script.
    pause
    exit /b 1
)

echo [1/3] Kiem tra phan vung active hien tai...
for /f "tokens=2 delims=: " %%a in ('fastboot getvar current-slot 2^>^&1 ^| findstr /i "current-slot:"') do set "SLOT=%%a"
if "%SLOT%"=="" set "SLOT=a"
echo     Active slot: %SLOT%

set "STOCK_IMG=stock_boot.img"
if not exist "%STOCK_IMG%" (
    if exist "boot.img" set "STOCK_IMG=boot.img"
    if exist "..\stock\boot.img" set "STOCK_IMG=..\stock\boot.img"
)

if not exist "%STOCK_IMG%" (
    echo [LOI] Khong tim thay file stock_boot.img hoac boot.img!
    pause
    exit /b 1
)

echo [2/3] Dang nap lai Stock Boot vao boot_%SLOT% tu %STOCK_IMG%...
fastboot flash boot_%SLOT% "%STOCK_IMG%"
if errorlevel 1 (
    echo [CANH BAO] Nap boot_%SLOT% khong thanh cong, thu nap boot tong quat...
    fastboot flash boot "%STOCK_IMG%"
)

echo [3/3] Khoi phuc hoan tat!
echo Nhan phim bat ky de khoi dong lai may vao he dieu hanh...
pause >nul
fastboot reboot
echo Done.
