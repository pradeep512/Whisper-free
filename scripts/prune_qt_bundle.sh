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

# These Qt artifacts are not used by Whisper-Free and materially increase
# licensing/compliance risk or third-party notice scope in release bundles.
REMOVE_PATHS=(
    "QtPdf"
    "QtQml"
    "QtQmlMeta"
    "QtQmlModels"
    "QtQmlWorkerScript"
    "QtQuick"
    "QtVirtualKeyboard"
    "QtVirtualKeyboardQml"
    "PySide6/Qt/lib/QtPdf.framework"
    "PySide6/Qt/lib/QtQml.framework"
    "PySide6/Qt/lib/QtQmlMeta.framework"
    "PySide6/Qt/lib/QtQmlModels.framework"
    "PySide6/Qt/lib/QtQmlWorkerScript.framework"
    "PySide6/Qt/lib/QtQuick.framework"
    "PySide6/Qt/lib/QtVirtualKeyboard.framework"
    "PySide6/Qt/lib/QtVirtualKeyboardQml.framework"
    "PySide6/Qt/plugins/imageformats/libqpdf.dylib"
    "PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.dylib"
)

for rel_path in "${REMOVE_PATHS[@]}"; do
    abs_path="$INTERNAL_ROOT/$rel_path"
    if [ -e "$abs_path" ] || [ -L "$abs_path" ]; then
        rm -rf "$abs_path"
        echo "Removed: $abs_path"
    fi
done

FORBIDDEN_PATTERNS=(
    "QtPdf"
    "QtQml.framework"
    "QtQmlMeta.framework"
    "QtQmlModels.framework"
    "QtQmlWorkerScript.framework"
    "QtQuick.framework"
    "QtVirtualKeyboard"
    "QtVirtualKeyboardQml"
    "libqpdf.dylib"
    "libqtvirtualkeyboardplugin.dylib"
)

remaining=0
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if find "$INTERNAL_ROOT" -path "*$pattern*" -print | grep -q .; then
        echo "Forbidden Qt artifact still present after prune: $pattern" >&2
        remaining=1
    fi
done

if [ "$remaining" -ne 0 ]; then
    exit 1
fi

echo "Qt bundle prune audit passed for: $TARGET"
