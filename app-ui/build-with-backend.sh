#!/usr/bin/env bash

# Build script for ClassFox with embedded backend on macOS.
# Usage: ./build-with-backend.sh [x86_64|arm64]

set -euo pipefail

GREEN='\033[0;32m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$ROOT_DIR/api-service"
TAURI_BACKEND_DIR="$SCRIPT_DIR/src-tauri/backend"
VENV_PYTHON="$API_DIR/.venv/bin/python"

ARCH="${1:-$(uname -m)}"
if [[ "$ARCH" == "arm64" || "$ARCH" == "aarch64" ]]; then
    TARGET="aarch64-apple-darwin"
    ARCH_LABEL="Apple Silicon (arm64)"
else
    TARGET="x86_64-apple-darwin"
    ARCH_LABEL="Intel (x86_64)"
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Missing Python virtualenv at $VENV_PYTHON"
    echo "Run: cd api-service && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install pyinstaller"
    exit 1
fi

if ! command -v rustup >/dev/null 2>&1; then
    if [[ -f "$HOME/.cargo/env" ]]; then
        # shellcheck disable=SC1090
        source "$HOME/.cargo/env"
    fi
fi

if ! command -v rustup >/dev/null 2>&1; then
    echo "rustup is required but not available in PATH."
    exit 1
fi

echo -e "${GREEN}🚀 Building ClassFox for ${ARCH_LABEL}...${NC}"

echo -e "${GREEN}📦 Building Python backend...${NC}"
cd "$API_DIR"
rm -rf dist build
CC=clang CXX=clang++ "$VENV_PYTHON" -m PyInstaller backend.spec --clean --noconfirm

echo -e "${GREEN}📋 Preparing backend resources for Tauri...${NC}"
rm -rf "$TAURI_BACKEND_DIR"
mkdir -p "$TAURI_BACKEND_DIR"
cp dist/class-assistant-backend "$TAURI_BACKEND_DIR/"
cp .env.example "$TAURI_BACKEND_DIR/"
chmod +x "$TAURI_BACKEND_DIR/class-assistant-backend"

echo -e "${GREEN}📦 Building Tauri frontend (${TARGET})...${NC}"
cd "$SCRIPT_DIR"
rustup target add "$TARGET"

echo -e "${GREEN}🧹 Cleaning Tauri target cache...${NC}"
rm -rf src-tauri/target

npm run tauri build -- --target "$TARGET"

echo -e "${GREEN}✅ Build complete!${NC}"
echo "Architecture: ${ARCH_LABEL}"
echo "App bundle: src-tauri/target/${TARGET}/release/bundle/macos/课狐ClassFox.app"
echo "DMG: src-tauri/target/${TARGET}/release/bundle/dmg/课狐ClassFox_1.2.0_${ARCH}.dmg"
