#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing $PYTHON. Create the project virtual environment first." >&2
  exit 1
fi

if ! "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
  echo "PyInstaller is not installed in the project virtual environment." >&2
  echo "Run: $PYTHON -m pip install pyinstaller" >&2
  exit 1
fi

cd "$PROJECT_DIR"
rm -rf build/Antilego dist/Antilego.app dist/Antilego-macOS-arm64.zip

"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name Antilego \
  --icon Antilego.app/Contents/Resources/AppIcon.icns \
  --osx-bundle-identifier com.tarikfilipovic.antilego.local \
  --target-architecture arm64 \
  --add-data "antilego/dashboard_static:antilego/dashboard_static" \
  --add-data "assets/antilego_logo_only.png:assets" \
  antilego_app.py

codesign --force --deep --sign - dist/Antilego.app
ditto -c -k --sequesterRsrc --keepParent \
  dist/Antilego.app dist/Antilego-macOS-arm64.zip

echo "Built $PROJECT_DIR/dist/Antilego-macOS-arm64.zip"
