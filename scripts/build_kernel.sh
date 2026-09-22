#!/usr/bin/env bash
# ==============================================================================
# songyuan-sukisu-builder: Automated Kernel Build Pipeline for WSL2 / Linux
# Target: Redmi K100 Pro Max (songyuan) / Snapdragon 8 Elite / Android 16 (6.12)
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# Default configuration
KERNEL_DIR="${1:-$PWD}"
SUSFS_BRANCH="${2:-susfs-main}"
HOOK_METHOD="${3:-kprobes}"
ENABLE_KPM="${4:-true}"
OUTPUT_DIR="${5:-$KERNEL_DIR/out}"

log_info "=== SukiSU Ultra Built-in Kernel Build Engine ==="
log_info "Target Directory: $KERNEL_DIR"
log_info "SUSFS Branch:     $SUSFS_BRANCH"
log_info "Hook Method:      $HOOK_METHOD"
log_info "KPM Enabled:      $ENABLE_KPM"
log_info "Output Directory: $OUTPUT_DIR"

# 1. Validate environment & dependencies
log_info "Step 1: Checking build dependencies..."
MISSING_DEPS=()
for dep in git curl make clang ld.lld python3 bc bison flex; do
    if ! command -v "$dep" &>/dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    log_err "Missing required dependencies: ${MISSING_DEPS[*]}"
    log_err "Run: sudo apt update && sudo apt install -y git curl build-essential libncurses-dev bison flex libssl-dev libelf-dev clang lld python3 bc"
    exit 1
fi
log_ok "All host dependencies satisfied."

# 2. Check kernel directory structure
cd "$KERNEL_DIR"
DRIVERS_DIR=""
if [ -d "common/drivers" ]; then
    DRIVERS_DIR="common/drivers"
elif [ -d "drivers" ]; then
    DRIVERS_DIR="drivers"
else
    log_err "Could not find drivers directory in $KERNEL_DIR"
    exit 1
fi
log_ok "Found kernel drivers directory: $DRIVERS_DIR"

# 3. Integrate SukiSU Ultra BUILT-IN
log_info "Step 2: Integrating SukiSU Ultra BUILT-IN into tree..."
SUKISU_SETUP_URL="https://raw.githubusercontent.com/SukiSU-Ultra/SukiSU-Ultra/main/kernel/setup.sh"

curl -LSs "$SUKISU_SETUP_URL" | bash -s builtin

if [ ! -d "KernelSU" ]; then
    log_err "KernelSU integration directory not found!"
    exit 1
fi

SUKISU_COMMIT=$(git -C KernelSU rev-parse HEAD 2>/dev/null || echo "unknown")
log_ok "SukiSU Ultra integrated (Commit: $SUKISU_COMMIT)"

# 4. Integrate SUSFS
if [ "$SUSFS_BRANCH" != "Disabled" ] && [ "$SUSFS_BRANCH" != "none" ]; then
    log_info "Step 3: Integrating SUSFS ($SUSFS_BRANCH)..."
    curl -LSs "$SUKISU_SETUP_URL" | bash -s "$SUSFS_BRANCH" || {
        log_warn "Branch '$SUSFS_BRANCH' failed with setup.sh, attempting susfs-main fallback..."
        curl -LSs "$SUKISU_SETUP_URL" | bash -s susfs-main
    }
    log_ok "SUSFS integrated successfully."
else
    log_info "Step 3: SUSFS integration skipped (Disabled)."
fi

# 5. Kernel Configuration (.config)
log_info "Step 4: Configuring kernel symbols..."
ARCH=arm64
export ARCH
export CROSS_COMPILE=aarch64-linux-gnu-
export CC=clang
export LD=ld.lld

if [ -f .config ]; then
    cp .config .config.bak
    log_info "Backed up existing .config to .config.bak"
else
    if [ -f "arch/arm64/configs/gki_defconfig" ]; then
        make ARCH=arm64 gki_defconfig
    else
        make ARCH=arm64 defconfig
    fi
fi

# Enable SukiSU Core
scripts/config --enable CONFIG_KSU

# Configure Hook
if [ "$HOOK_METHOD" = "manual" ]; then
    scripts/config --enable CONFIG_KSU_MANUAL_HOOK
    scripts/config --disable CONFIG_KPROBES
elif [ "$HOOK_METHOD" = "tracepoint" ]; then
    scripts/config --enable CONFIG_TRACEPOINTS
    scripts/config --disable CONFIG_KSU_MANUAL_HOOK
else
    # Default: kprobes
    scripts/config --enable CONFIG_KPROBES
    scripts/config --enable CONFIG_HAVE_KPROBES
    scripts/config --enable CONFIG_KPROBE_EVENTS
    scripts/config --disable CONFIG_KSU_MANUAL_HOOK
fi

# Enforce KPM
if [ "$ENABLE_KPM" = "true" ]; then
    scripts/config --enable CONFIG_KPM
fi

# Refresh configuration
log_info "Running make olddefconfig..."
make ARCH=arm64 olddefconfig

# Strict Verification
if ! grep -q "^CONFIG_KSU=y" .config; then
    log_err "CRITICAL: CONFIG_KSU=y is missing from .config!"
    exit 1
fi

if [ "$ENABLE_KPM" = "true" ] && ! grep -q "^CONFIG_KPM=y" .config; then
    log_err "CRITICAL: CONFIG_KPM=y is missing from .config! Build aborted per safety rules."
    exit 1
fi
log_ok "Kernel configuration verified successfully."

# 6. Build Kernel Image
log_info "Step 5: Compiling arm64 kernel Image..."
NPROC=$(nproc)
log_info "Building with $NPROC parallel threads..."

make -j"$NPROC" ARCH=arm64 CC=clang LD=ld.lld Image

BUILT_IMAGE="arch/arm64/boot/Image"
if [ ! -f "$BUILT_IMAGE" ]; then
    log_err "Build failed: $BUILT_IMAGE was not generated!"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
cp "$BUILT_IMAGE" "$OUTPUT_DIR/Image"
SHA256=$(sha256sum "$OUTPUT_DIR/Image" | awk '{print $1}')
echo "$SHA256" > "$OUTPUT_DIR/Image.sha256"

log_ok "=== BUILD FINISHED SUCCESSFULLY ==="
log_ok "Artifact: $OUTPUT_DIR/Image"
log_ok "SHA256:   $SHA256"
