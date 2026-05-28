# Whisper-Free Qt / PySide6 LGPL Compliance Review

Verified on: May 28, 2026

This document explains what was checked, what was found, and what Whisper-Free can do to reduce LGPL compliance risk. It is written in simple English. It is a technical compliance review, not legal advice.

## Short answer

Whisper-Free uses `PySide6`, which brings in Qt for Python and Qt runtime files. That is normal.

The main problem is not "commercial use" by itself. The main problem is how the packaged app is distributed.

The most important finding is this:

- The source code only uses basic Qt modules.
- But the built macOS bundle currently ships extra Qt modules that were not directly used by the source.
- One of those extra modules is `Qt Virtual Keyboard`, and Qt's official licensing page lists `Qt Virtual Keyboard` as a GPL-only module for open-source use.

That makes the current packaged app a high-risk release from a Qt licensing point of view.

## Scope of this review

This review checked:

- The repository source code
- The PyInstaller packaging files
- The current `dist/` output that exists in this repo
- Qt's official documentation pages for Qt licensing, Qt for Python licensing, Qt WebEngine licensing, Qt PDF licensing, and Qt Assistant licensing

This review did not check:

- Any binary that is not present in this repo
- Any private release asset that is not in `dist/`
- Any legal contract you may have with The Qt Company

## What was verified locally

### 1. Whisper-Free uses PySide6

Verified in:

- `requirements-base.txt`

Current repo evidence:

- `PySide6>=6.5.0` is declared in `requirements-base.txt:5`

Meaning:

- Whisper-Free uses Qt through the `PySide6` Python package.
- You did not need to install a separate standalone Qt SDK for the app to use Qt runtime files.
- But from a licensing point of view, this still counts as using Qt.

### 2. The source code directly imports only four PySide6 modules

Verified by searching all `PySide6` imports in `app/`, `scripts/`, and `packaging/`.

Directly used PySide6 modules found:

- `QtCore`
- `QtGui`
- `QtNetwork`
- `QtWidgets`

Meaning:

- The source code itself does not directly import `QtWebEngine`, `QtDesigner`, `QtLinguist`, `QtAssistant`, `QtQuick3D`, `QtCoAP`, `QtMQTT`, `QtHttpServer`, or other obvious special modules.

### 3. The source code does not show direct use of Qt's GPL-only modules

Qt's official Qt 6 licensing page lists these GPL-only modules for open-source use:

- Qt Canvas Painter
- Qt CoAP
- Qt Graphs
- Qt GRPC
- Qt HTTP Server
- Qt Lottie Animation
- Qt MQTT
- Qt Network Authorization
- Qt Qml Compiler
- Qt Quick 3D
- Qt Quick 3D Physics
- Qt Quick Timeline
- Qt Virtual Keyboard
- Qt Wayland Compositor

From the source code alone, none of those modules were directly imported.

### 4. The macOS build output in `dist/` ships more Qt content than the source code uses

Verified by searching the existing `dist/Whisper-Free/_internal/PySide6` tree.

The current bundle includes at least these Qt runtime pieces:

- `QtCore`
- `QtGui`
- `QtWidgets`
- `QtNetwork`
- `QtDBus`
- `QtQml`
- `QtQmlMeta`
- `QtQmlModels`
- `QtQmlWorkerScript`
- `QtQuick`
- `QtOpenGL`
- `QtSvg`
- `QtPdf`
- `QtVirtualKeyboard`
- `QtVirtualKeyboardQml`
- many Qt plugins
- many Qt translation files

Meaning:

- The built app bundle is broader than the source code.
- Compliance should be judged on what is actually distributed, not only on what is imported in Python.

### 5. The built bundle currently includes Qt Virtual Keyboard pieces

Verified in `dist/`:

- `dist/Whisper-Free/_internal/PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.dylib`
- `dist/Whisper-Free/_internal/PySide6/Qt/lib/QtVirtualKeyboard.framework/...`
- `dist/Whisper-Free/_internal/PySide6/Qt/lib/QtVirtualKeyboardQml.framework/...`

Meaning:

- Even though the app source code does not directly import `Qt Virtual Keyboard`, the current packaged macOS build still ships it.

This matters because Qt's official licensing page lists `Qt Virtual Keyboard` as GPL-only for open-source use.

### 6. The built bundle does not appear to ship Qt Assistant, Qt Designer, Qt Linguist, or QtWebEngineProcess

Verified by searching the current `dist/` tree.

Not found in `dist/`:

- `Assistant`
- `Designer`
- `Linguist`
- `QtWebEngineProcess`

Meaning:

- Those scanner hits are probably coming from the local Python environment, not from the app bundle itself.

### 7. Those extra tool executables do exist in the local `venv`

Verified under `venv/lib/python3.11/site-packages/PySide6`:

- `Assistant.app`
- `Designer.app`
- `Linguist.app`
- `QtWebEngineCore.framework` in the local PySide6 install

Meaning:

- If a scanner looked at your Python environment instead of your built app, it would report those items.
- That is different from proving that your shipped app contains them.

### 8. Repo-level notices and license status

Verified by searching the repo root for standard names.

Current state after remediation work:

- top-level `LICENSE` file added for Whisper-Free application code
- `THIRD_PARTY_NOTICES.md` added
- `licenses/LGPL-3.0.txt` added
- `licenses/GPL-3.0.txt` added

Meaning:

- The repository now has a declared app license and third-party notice materials.

### 9. The About panel license wording

Verified in:

- `app/ui/main_window.py:258`

Current state after remediation work:

- the About panel now says the app code is MIT
- it also says bundled PySide6 / Qt runtime components are under their own licenses

Meaning:

- The UI no longer implies that the entire bundled distribution is covered only by MIT.

### 10. Packaging of notice materials

Verified in:

- `packaging/macos/Whisper-Free.spec`

Current state after remediation work:

- the macOS spec now includes:
  - `THIRD_PARTY_NOTICES.md`
  - `licenses/README.md`
  - `licenses/LGPL-3.0.txt`
  - `licenses/GPL-3.0.txt`
- the Linux/AppImage spec now includes the same notice bundle

### 11. Release-bundle notice status

Verified by searching `dist/` for `LICENSE`, `COPYING`, and `NOTICE`.

Some third-party license files are present for other packages, but no obvious Qt or PySide license bundle was found through standard file-name search.

Meaning:

- Future builds from the updated specs should include the Qt/PySide notice bundle.

### 12. The current macOS bundle is not statically linking PySide6 / Qt into one single binary

Verified by checking:

- the main executable format
- the runtime link table of the main executable
- the runtime link table of shipped PySide6 extension modules
- the presence of separate `.dylib`, `.so`, and `.framework` files in the bundle

What was found:

- `dist/Whisper-Free/Whisper-Free` is a normal Mach-O executable
- the bundle contains separate Qt and PySide6 runtime files, including:
  - `libpyside6.abi3.6.11.dylib`
  - `QtCore.abi3.so`
  - `QtGui.abi3.so`
  - `QtWidgets.abi3.so`
  - separate Qt frameworks such as `QtCore.framework`, `QtGui.framework`, `QtWidgets.framework`, and `QtNetwork.framework`
- `QtWidgets.abi3.so` dynamically links against:
  - `@rpath/libpyside6.abi3.6.11.dylib`
  - `@rpath/QtWidgets`
  - `@rpath/QtGui`
  - `@rpath/QtCore`

Meaning:

- The current packaged macOS app is not a single statically linked Qt blob.
- Qt and PySide6 are shipped as separate runtime libraries and frameworks inside the app bundle.
- That is generally better for LGPL-style replaceability than static linking.
- However, this does not by itself solve every compliance issue. It does not remove the need for proper notices, and it does not solve the separate risk created by shipping `Qt Virtual Keyboard`.

## What was verified from official Qt documentation

### 1. Qt for Python has both community and commercial paths

Qt for Python official docs say:

- Qt for Python is available under LGPLv3/GPLv3 and under the Qt commercial license.
- There is a Community Edition and a Commercial Edition.

Meaning:

- Using `pip install pyside6` normally puts you on the community open-source path, not the commercial package path.

### 2. Commercial use is not automatically forbidden

Qt's licensing docs say:

- Qt under LGPLv3 is allowed if you comply with LGPLv3 terms.
- Commercial licensing is needed if you do not want to comply with the open-source obligations or cannot comply with them.

Meaning:

- Open-source or commercial projects can use community Qt/PySide, but they must follow the open-source license terms.
- The issue is compliance, not just whether money is involved.

### 3. Qt's official commercial-use page for Qt for Python says commercial users should not rely on `pip install pyside6` for the commercial route

Qt's Qt for Python commercial page says commercial users should not install the Community Edition via `pip install pyside6` and should use the official commercial package sources instead.

Meaning:

- If Whisper-Free wants to rely on a paid commercial Qt license, the current community-package setup is the wrong path.
- If Whisper-Free stays on the community route, it must comply with the open-source license obligations.

### 4. Qt lists some modules as GPL-only for open-source use

Qt's official Qt 6 licensing page says some modules are not available under LGPLv3, but only under GPL.

One of those modules is:

- `Qt Virtual Keyboard`

Meaning:

- Shipping `Qt Virtual Keyboard` inside the app bundle is a special risk.

### 5. Qt tools and utilities are treated differently

Qt's official licensing page says Qt tools and utilities are available under commercial terms or under GPLv3 with the Qt GPL exception.

Meaning:

- If `Assistant`, `Designer`, or `Linguist` were shipped inside the app, that would need separate attention.
- In this repo, those tools were found in `venv/` but not in the current `dist/` output.

### 6. Qt PDF has its own licensing and third-party obligations

Qt's official Qt PDF licensing page says:

- Qt PDF is available under commercial terms, or LGPLv3, or GPLv2.
- It includes PDFium and other third-party code with extra licenses.

Meaning:

- Shipping `QtPdf` is not automatically forbidden.
- But it adds more notice and third-party license work.
- The current build includes `QtPdf` even though the source code does not clearly show direct use of it.

## Risk assessment

### High risk: current macOS bundle ships `Qt Virtual Keyboard`

Why this matters:

- `Qt Virtual Keyboard` is listed by Qt as GPL-only for open-source use.
- The current app bundle ships `QtVirtualKeyboard` files.
- Whisper-Free does not appear to be distributed as a GPLv3 application.
- There is no evidence in this repo of a Qt commercial package setup.

Plain English:

- This is the biggest current licensing risk.
- If you distribute the current macOS bundle as-is, this is the first thing to fix.

### Medium risk: notice coverage still needs rebuild verification

Why this matters:

- The repo and packaging scripts have now been updated.
- But a fresh clean rebuild should still be run and inspected to confirm the release artifact really contains the notice files.

Plain English:

- The notice story is much better now, but it still needs a full release rebuild check.

### Medium risk: public source code helps, but it is not enough by itself

Why this matters:

- Making your own application source code public is helpful.
- Shipping shared libraries instead of a statically linked blob is also helpful.
- But those facts alone do not automatically make the release compliant.

Plain English:

- Public GitHub source and dynamic libraries reduce risk.
- They do not automatically fix missing notices, missing license texts, or shipping a Qt module that is only available under GPL for open-source use.

### Medium risk: the bundle includes unused extra Qt modules

Why this matters:

- The source uses only four direct Qt modules.
- The bundle ships many more modules and plugins.

Plain English:

- Extra shipped modules create extra compliance work and extra risk.
- If a module is not needed, it should not be shipped.

### Low risk: scanner hits for Assistant, Designer, Linguist, and QtWebEngineProcess

Why this matters:

- These were found in the local Python environment.
- They were not found in the current `dist/` output.

Plain English:

- These scanner hits are not currently the main problem.
- They should still be watched in future release audits.

## Answer to the PySide6 commercial-use question

Based on what was verified:

- There is no clear sign that Whisper-Free violated a paid Qt commercial subscription.
- The repo appears to use the community `PySide6` package path.
- That means the real issue is open-source license compliance for what you distribute.

Plain English:

- The current problem is not "you forgot to buy Qt."
- The current problem is "your release bundle and notices need work, and your bundle currently ships at least one Qt module that is likely not safe for your current licensing path."

## What Whisper-Free should do now

### Priority 1: stop shipping the current macOS bundle until `Qt Virtual Keyboard` is removed or the licensing path changes

Recommended action:

- Do not treat the current bundled macOS artifact as clean.
- Remove `QtVirtualKeyboard` and related unused Qt pieces from the release build.

Safer target:

- The release should ideally contain only the Qt runtime pieces the app really needs.

### Priority 2: rebuild in a clean packaging environment and audit the output

Recommended action:

- Build from a clean virtual environment.
- After every build, scan the finished `dist/` tree and make a list of all shipped Qt frameworks, plugins, and helper executables.

Why:

- Right now the build ships more Qt content than the source code suggests.
- This needs to become visible and repeatable.

### Priority 3: explicitly exclude unused Qt modules and plugins in packaging

Recommended action:

- Tighten the PyInstaller packaging process so it excludes unused Qt modules, QML pieces, plugins, and translation packs.

Focus first on removing:

- `QtVirtualKeyboard`
- `QtVirtualKeyboardQml`
- unused QML and Qt Quick pieces if the app does not need them
- unused plugins and translations

Why:

- Fewer shipped Qt components means less legal risk and less release size.

### Priority 4: verify the new license and notice set in fresh release artifacts

Status:

- completed in the repository:
  - top-level `LICENSE` file added
  - `THIRD_PARTY_NOTICES.md` added
  - LGPL and GPL license texts added
  - packaging specs updated to include them

Next action:

- run a clean rebuild and confirm the packaged app actually contains these files

Why:

- Users need clear notice that the app includes third-party licensed software.
- The current "MIT License" message is too incomplete.

### Priority 5: verify About panel and README updates in the next release

Status:

- completed in the repository:
  - About panel wording updated
  - README licensing section added

Why:

- The current app messaging hides third-party license obligations.

### Priority 6: keep exact source and notice material for every release

Recommended action:

- For every release, keep:
  - the exact app source used for that release
  - the exact packaging scripts
  - the exact third-party notice bundle
  - a machine-readable or human-readable list of shipped Qt components

Why:

- If someone asks how a release was built or what it contains, you need a clear answer.

### Priority 7: if you want the commercial Qt route, change the dependency and build path

Recommended action:

- If you decide not to manage LGPL/GPL obligations, move to the official commercial Qt for Python package route instead of the community `pip install pyside6` path.

Why:

- Qt's own commercial-use docs say the commercial route should not rely on the community wheel from `pip install pyside6`.

## Practical release checklist

Before shipping a future release:

1. Build in a clean environment.
2. Scan the final bundle for every shipped Qt framework, plugin, translation pack, and helper executable.
3. Confirm that no GPL-only Qt module is present unless you intentionally chose a GPL or commercial route.
4. Confirm that no unwanted Qt tools are present.
5. Confirm that the release bundle includes your app license and third-party notice files.
6. Confirm that the About panel and README match the real licensing story.
7. Archive the exact source, build script, and notice files used for the release.

## Bottom line

What looks okay:

- The source code directly uses normal PySide6 modules.
- The scanner hits for `Assistant`, `Designer`, `Linguist`, and `QtWebEngineProcess` do not appear in the current `dist/` bundle.
- There is no clear evidence of a Qt commercial subscription breach.

What needs attention:

- The current macOS bundle ships `Qt Virtual Keyboard`, which is a high-risk finding because Qt lists it as GPL-only for open-source use.
- The bundle also ships extra Qt modules that increase compliance work.
- The repo and release do not currently show a strong Qt/PySide notice and license story.
- The app's About panel currently oversimplifies licensing by saying only "MIT License".

## Official sources used in this review

- Qt Licensing: https://doc.qt.io/qt-6/licensing.html
- Qt for Python overview: https://doc.qt.io/qtforpython-6.5/index.html
- Qt for Python commercial use: https://doc.qt.io/qtforpython-6.6/commercial/index.html
- Qt for Python licenses used: https://doc.qt.io/qtforpython-6/licenses.html
- Qt for Python LGPL text: https://doc.qt.io/qtforpython-6/overviews/qtdoc-lgpl.html
- Qt open-source licensing FAQ: https://www.qt.io/faq/qt-open-source-licensing
- Qt PDF licensing: https://doc.qt.io/qt-6/qtpdf-licensing.html
- Qt WebEngine licensing: https://doc.qt.io/qt-6/qtwebengine-licensing.html
- Qt Assistant licensing: https://doc.qt.io/qt-6/assistant-licenses.html

## Local evidence used in this review

- `requirements-base.txt`
- `app/main.py`
- `app/core/ipc_server.py`
- `app/ui/main_window.py`
- `packaging/macos/Whisper-Free.spec`
- current contents of `dist/Whisper-Free/_internal/PySide6`
- current contents of `venv/lib/python3.11/site-packages/PySide6`
