#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <app-bundle-or-onedir-path>" >&2
    exit 64
fi

TARGET="$1"

if [ -d "$TARGET/Contents/Resources/_internal/PySide6" ]; then
    INTERNAL_ROOT="$TARGET/Contents/Resources/_internal"
elif [ -d "$TARGET/_internal/PySide6" ]; then
    INTERNAL_ROOT="$TARGET/_internal"
else
    echo "Error: could not locate bundled PySide6 runtime under: $TARGET" >&2
    exit 1
fi

echo "Qt frameworks:"
find "$INTERNAL_ROOT/PySide6/Qt/lib" -maxdepth 1 -type d -name 'Qt*.framework' | sort
echo ""
echo "Qt plugins:"
find "$INTERNAL_ROOT/PySide6/Qt/plugins" -type f | sort
