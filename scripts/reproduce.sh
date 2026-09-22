#!/usr/bin/env bash
# ==============================================================================
# songyuan-sukisu-builder: Reproducible Build Verification Script
# Freezes timestamps, flags, and git references to ensure identical hash reproduction
# ==============================================================================

set -euo pipefail

KERNEL_DIR="${1:-$PWD}"
REFERENCE_SHA256="${2:-}"

export KBUILD_BUILD_TIMESTAMP="Fri Aug 15 00:00:00 UTC 2026"
export KBUILD_BUILD_USER="android-build"
export KBUILD_BUILD_HOST="build-server"
export SOURCE_DATE_EPOCH=1786752000

echo "=== Reproducible Build Verification ==="
echo "Kernel Dir:  $KERNEL_DIR"
echo "Timestamp:   $KBUILD_BUILD_TIMESTAMP"
echo "User/Host:   $KBUILD_BUILD_USER@$KBUILD_BUILD_HOST"

cd "$KERNEL_DIR"

# 1. Output commit references
echo "--- Git References ---"
echo "Kernel HEAD:  $(git rev-parse HEAD 2>/dev/null || echo 'N/A')"
if [ -d "KernelSU" ]; then
    echo "KernelSU SHA: $(git -C KernelSU rev-parse HEAD 2>/dev/null || echo 'N/A')"
fi

# 2. Build kernel Image
make -j"$(nproc)" ARCH=arm64 CC=clang LD=ld.lld Image

BUILT_IMAGE="arch/arm64/boot/Image"
if [ ! -f "$BUILT_IMAGE" ]; then
    echo "[ERROR] Kernel Image not found!" >&2
    exit 1
fi

BUILT_SHA256=$(sha256sum "$BUILT_IMAGE" | awk '{print $1}')
echo "Reproduced Image SHA256: $BUILT_SHA256"

if [ -n "$REFERENCE_SHA256" ]; then
    if [ "$BUILT_SHA256" = "$REFERENCE_SHA256" ]; then
        echo "[SUCCESS] Hash MATCHES reference exactly! Build is 100% reproducible."
        exit 0
    else
        echo "[MISMATCH] Hash differs from reference ($REFERENCE_SHA256 vs $BUILT_SHA256)" >&2
        exit 1
    fi
fi
