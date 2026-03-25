#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"

echo "[SecureLink] Build root: $ROOT_DIR"
echo "[SecureLink] Python: $PYTHON_BIN"

cd "$ROOT_DIR"

"$PYTHON_BIN" -m pip install --upgrade pip pyinstaller

rm -rf build dist

echo "[SecureLink] Building one-dir from spec..."
"$PYTHON_BIN" -m PyInstaller --noconfirm SecureLink.spec

echo "[SecureLink] Building one-file fallback..."
"$PYTHON_BIN" -m PyInstaller --noconfirm --onefile --windowed --name SecureLinkOneFile seclink_main.py

echo "[SecureLink] Build complete"
echo "Artifacts:"
echo "  - dist/SecureLink/"
echo "  - dist/SecureLinkOneFile"
