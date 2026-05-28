# Third-Party Notices

Last reviewed: May 28, 2026

This file documents third-party license information for Whisper-Free distributions.

Whisper-Free's own application source code is licensed under MIT. See the top-level `LICENSE` file.

This document covers third-party components that are bundled with or used by Whisper-Free distributions.

## PySide6 / Qt for Python

Whisper-Free uses `PySide6` to provide the Qt desktop UI runtime.

Verified in this repository:

- `requirements-base.txt` declares `PySide6>=6.5.0`
- the source code directly imports `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtNetwork`, and `PySide6.QtWidgets`

Relevant upstream licensing pages:

- Qt Licensing: https://doc.qt.io/qt-6/licensing.html
- Qt for Python overview: https://doc.qt.io/qtforpython-6.5/index.html
- Commercial Use - Qt for Python: https://doc.qt.io/qtforpython-6/commercial/index.html
- Licenses Used in Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html

Key points:

- Qt for Python is available through a Community Edition and a Commercial Edition.
- The community `pip install pyside6` path is the open-source distribution path.
- The Qt Company states that commercial users should not rely on the community `pip install pyside6` distribution if they intend to use the commercial licensing route.
- For open-source use, Qt is generally available under LGPLv3, but some Qt modules are GPL-only.

## Qt modules used and shipped

Directly used by Whisper-Free source code:

- `QtCore`
- `QtGui`
- `QtNetwork`
- `QtWidgets`

Whisper-Free's macOS packaging has been tightened so the final bundle keeps only the core desktop Qt runtime needed by the app and prunes unused high-risk extras such as:

- `QtVirtualKeyboard`
- `QtVirtualKeyboardQml`
- `QtPdf`
- `QtQml`
- `QtQuick`

This pruning is enforced by:

- `packaging/macos/Whisper-Free.spec`
- `scripts/prune_qt_bundle.sh`
- `scripts/audit_qt_bundle.sh`

## Included license texts

The following license text files are included in this repository for distribution packaging and notice purposes:

- `licenses/LGPL-3.0.txt`
- `licenses/GPL-3.0.txt`

These texts were downloaded from the GNU project:

- https://www.gnu.org/licenses/lgpl-3.0.txt
- https://www.gnu.org/licenses/gpl-3.0.txt

## Other third-party components

Whisper-Free also depends on other open-source packages besides PySide6 / Qt, including audio, ML, packaging, and platform integration libraries.

The built app bundles some of those dependencies and their native libraries. Some packages already ship their own license files inside the built output. If Whisper-Free distributions are meant for public release, release engineering should continue auditing bundled dependencies and collecting their notices into a single release notice set.

## Recommended release practice

For each release:

1. Build in a clean virtual environment.
2. Audit the final bundle contents.
3. Confirm that no GPL-only Qt module is present unless intentionally using a GPL or commercial Qt path.
4. Bundle this file and the `licenses/` directory into release artifacts.
5. Keep an archived copy of the exact source, build scripts, and notice files used for that release.
