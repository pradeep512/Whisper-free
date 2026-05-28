#!/usr/bin/env bash
# Build Whisper-Free.app and Whisper-Free.dmg on macOS.
#
# Prerequisites (one-time):
#   brew install create-dmg ffmpeg
#   python3.11 -m venv venv
#   source venv/bin/activate
#   pip install -r requirements-macos.txt
#
# Usage:
#   ./scripts/build_macos.sh              # auto-detect version
#   VERSION=1.0.1 ./scripts/build_macos.sh
#
# Outputs:
#   dist/Whisper-Free.app
#   dist/Whisper-Free-${VERSION}.dmg
#   dist/Whisper-Free-${VERSION}.dmg.sha256

set -euo pipefail

# --- Resolve paths -----------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

# --- Sanity checks -----------------------------------------------------------

if [ "$(uname)" != "Darwin" ]; then
    echo "Error: this build script is macOS-only." >&2
    exit 1
fi

ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
    echo "Warning: architecture is '$ARCH', not 'arm64'. Whisper-Free on macOS" >&2
    echo "         is Apple-Silicon-only; the build may fail or produce a" >&2
    echo "         non-functional binary on Intel Macs." >&2
fi

if [ ! -d "venv" ]; then
    echo "Error: venv/ not found." >&2
    echo "  python3.11 -m venv venv" >&2
    echo "  source venv/bin/activate" >&2
    echo "  pip install -r requirements-macos.txt" >&2
    exit 1
fi

# Activate the venv so pyinstaller / sips / create-dmg run with our deps.
# shellcheck source=/dev/null
source venv/bin/activate

for tool in pyinstaller create-dmg sips iconutil shasum; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Error: required tool '$tool' not found in PATH." >&2
        if [ "$tool" = "create-dmg" ]; then
            echo "  brew install create-dmg" >&2
        elif [ "$tool" = "pyinstaller" ]; then
            echo "  pip install pyinstaller" >&2
        fi
        exit 1
    fi
done

# --- Resolve version ---------------------------------------------------------

if [ -z "${VERSION:-}" ]; then
    # Pull from app/ui/main_window.py "Version X.Y.Z" label.
    VERSION="$(grep -oE 'Version [0-9]+\.[0-9]+\.[0-9]+' app/ui/main_window.py \
              | head -1 \
              | sed 's/Version //')"
    if [ -z "$VERSION" ]; then
        VERSION="0.0.0-dev"
    fi
fi
echo "==> Building Whisper-Free v${VERSION} on ${ARCH}..."

# --- Generate .icns if missing or stale --------------------------------------

ICNS="assets/app-icon.icns"
SRC_PNG="assets/app-icon.png"

if [ ! -f "$ICNS" ] || [ "$SRC_PNG" -nt "$ICNS" ]; then
    echo "==> Generating $ICNS from $SRC_PNG"
    ICONSET="$(mktemp -d)/Whisper-Free.iconset"
    mkdir -p "$ICONSET"

    # Each iconset PNG must be exactly the listed dimensions. sips's --resampleHeightWidth
    # forces non-aspect-preserving resize; for non-square source PNGs this stretches.
    # Acceptable for placeholder; replace assets/app-icon.png with a 1024x1024 square
    # for production quality.
    for spec in \
        "16,icon_16x16.png" \
        "32,icon_16x16@2x.png" \
        "32,icon_32x32.png" \
        "64,icon_32x32@2x.png" \
        "128,icon_128x128.png" \
        "256,icon_128x128@2x.png" \
        "256,icon_256x256.png" \
        "512,icon_256x256@2x.png" \
        "512,icon_512x512.png" \
        "1024,icon_512x512@2x.png"
    do
        SIZE="${spec%%,*}"
        NAME="${spec##*,}"
        sips -z "$SIZE" "$SIZE" "$SRC_PNG" --out "$ICONSET/$NAME" >/dev/null
    done

    iconutil -c icns "$ICONSET" -o "$ICNS"
    rm -rf "$(dirname "$ICONSET")"
fi

# --- Clean previous build ----------------------------------------------------

echo "==> Cleaning build/ and dist/"
rm -rf build dist

# --- Run PyInstaller ---------------------------------------------------------

echo "==> Running PyInstaller (this takes a few minutes)..."
pyinstaller \
    --noconfirm \
    --clean \
    --log-level WARN \
    packaging/macos/Whisper-Free.spec

APP="dist/Whisper-Free.app"
if [ ! -d "$APP" ]; then
    echo "Error: build failed; $APP not found." >&2
    exit 1
fi

echo "==> Pruning unused Qt runtime components..."
"$ROOT/scripts/prune_qt_bundle.sh" "$APP"

# --- Bundle audits -----------------------------------------------------------

APP_SIZE_HUMAN="$(du -sh "$APP" | cut -f1)"
echo "==> Built $APP ($APP_SIZE_HUMAN)"

# Confirm critical Info.plist keys.
echo "==> Verifying Info.plist..."
PLIST="$APP/Contents/Info.plist"
for key in LSUIElement LSMinimumSystemVersion NSMicrophoneUsageDescription CFBundleIdentifier; do
    value="$(plutil -extract "$key" raw "$PLIST" 2>/dev/null || echo "MISSING")"
    if [ "$value" = "MISSING" ]; then
        echo "  ⚠ $key: missing" >&2
    else
        echo "  ✓ $key: $value"
    fi
done

# Confirm arm64 binary.
ARCH_INFO="$(file "$APP/Contents/MacOS/Whisper-Free")"
if echo "$ARCH_INFO" | grep -q 'arm64'; then
    echo "  ✓ binary is arm64"
else
    echo "  ⚠ binary architecture unexpected: $ARCH_INFO" >&2
fi

# Warn if torch slipped in.
if find "$APP" -name 'libtorch*' -o -name 'torch' 2>/dev/null | grep -q .; then
    echo "  ⚠ torch detected in bundle — excludes in spec may be off" >&2
fi

echo "==> Auditing bundled Qt runtime..."
"$ROOT/scripts/audit_qt_bundle.sh" "$APP"

# --- Build DMG ---------------------------------------------------------------

DMG="dist/Whisper-Free-${VERSION}.dmg"
rm -f "$DMG"

echo "==> Creating $DMG..."
create-dmg \
    --volname "Whisper-Free ${VERSION}" \
    --volicon "$ICNS" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "Whisper-Free.app" 175 190 \
    --hide-extension "Whisper-Free.app" \
    --app-drop-link 425 190 \
    --no-internet-enable \
    "$DMG" \
    "$APP"

DMG_SIZE_HUMAN="$(du -sh "$DMG" | cut -f1)"
echo "==> Built $DMG ($DMG_SIZE_HUMAN)"

# --- SHA256 ------------------------------------------------------------------

echo "==> Computing SHA256..."
shasum -a 256 "$DMG" | tee "$DMG.sha256"

# --- Done --------------------------------------------------------------------

echo ""
echo "Done."
echo "  App: $APP ($APP_SIZE_HUMAN)"
echo "  DMG: $DMG ($DMG_SIZE_HUMAN)"
echo ""
echo "Test the bundle:"
echo "  open $APP"
echo ""
echo "Test the DMG:"
echo "  open $DMG"
