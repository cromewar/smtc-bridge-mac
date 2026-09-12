#!/bin/sh
# Builds dist/SMTC Bridge.app with PyInstaller inside the uv-managed environment.
set -eu
cd "$(dirname "$0")"

echo "--- Syncing dependencies ---"
uv sync --group dev

echo "--- Running tests ---"
uv run pytest -q

echo "--- Cleaning old builds ---"
rm -rf build dist

echo "--- Building app bundle ---"
uv run pyinstaller --noconfirm smtc-bridge-mac.spec

APP="dist/SMTC Bridge.app"
echo "--- Signing (ad-hoc) ---"
# Ad-hoc signature so the bundle launches locally on Apple Silicon. For public distribution
# replace "-" with a Developer ID identity and notarize with `xcrun notarytool`.
codesign --force --deep --sign "${CODESIGN_IDENTITY:--}" "$APP"

echo
echo "--- Build complete: $APP ---"
