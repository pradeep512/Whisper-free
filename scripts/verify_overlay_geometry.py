#!/usr/bin/env python3
"""Verify DynamicIslandOverlay placement on the real connected displays.

This script intentionally uses the default Qt platform plugin. Do not run it
with QT_QPA_PLATFORM=offscreen: it needs real QScreen geometry and DPR data.
It prints a per-screen PASS/FAIL table and saves PNG evidence under
ralph/logs/overlay-evidence/.
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.ui.overlay import DynamicIslandOverlay, OverlayMode


EVIDENCE_DIR = REPO_ROOT / "ralph/logs/overlay-evidence"
POSITION = "top-center"
EXPECTED_WIDTH = DynamicIslandOverlay.MODE_CONFIGS[OverlayMode.LISTENING][0]
EXPECTED_HEIGHT = DynamicIslandOverlay.MODE_CONFIGS[OverlayMode.LISTENING][1]
EXPECTED_TOP_PADDING = 8


def _process_events_for(app: QApplication, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _rect_to_str(rect) -> str:
    return f"{rect.x()},{rect.y()} {rect.width()}x{rect.height()}"


def _repo_relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _verify_screen(app: QApplication, overlay: DynamicIslandOverlay, screen_index: int):
    screen = app.screens()[screen_index]
    dpr = float(screen.devicePixelRatio())
    tolerance = max(2, math.ceil(2 / max(dpr, 1.0)))

    overlay.set_position(POSITION, screen_index)
    overlay.update_waveform(
        [0.20, 0.45, 0.65, 0.35, 0.80, 0.55, 0.25, 0.70] * 3
    )
    overlay.set_mode(OverlayMode.LISTENING)
    overlay.show()
    overlay.raise_()

    _process_events_for(app, 0.8)
    overlay._correct_geometry_to_frame()
    overlay.repaint()
    app.processEvents()

    frame = overlay.frameGeometry()
    available = screen.availableGeometry()

    expected_center_x = available.x() + available.width() / 2
    actual_center_x = frame.x() + frame.width() / 2
    center_delta = abs(actual_center_x - expected_center_x)
    top_delta = abs(frame.y() - (available.y() + EXPECTED_TOP_PADDING))
    width_delta = abs(frame.width() - EXPECTED_WIDTH)
    height_delta = abs(frame.height() - EXPECTED_HEIGHT)

    overlay_grab_path = EVIDENCE_DIR / f"overlay-screen{screen_index}.png"
    screen_grab_path = EVIDENCE_DIR / f"overlay-screen{screen_index}-desktop.png"
    overlay.grab().save(str(overlay_grab_path), "PNG")
    screen.grabWindow(0).save(str(screen_grab_path), "PNG")

    cancel_rect = overlay._cancel_btn_rect
    stop_rect = overlay._stop_btn_rect
    controls_ok = (
        cancel_rect is not None
        and stop_rect is not None
        and overlay.rect().contains(cancel_rect)
        and overlay.rect().contains(stop_rect)
        and cancel_rect.width() >= 20
        and cancel_rect.height() >= 20
        and stop_rect.width() >= 20
        and stop_rect.height() >= 20
    )

    passed = (
        center_delta <= tolerance
        and top_delta <= tolerance
        and width_delta <= tolerance
        and height_delta <= tolerance
        and controls_ok
    )

    return {
        "index": screen_index,
        "name": screen.name(),
        "geometry": _rect_to_str(screen.geometry()),
        "available": _rect_to_str(available),
        "dpr": dpr,
        "frame": _rect_to_str(frame),
        "center_delta": center_delta,
        "top_delta": top_delta,
        "size_delta": f"{width_delta}x{height_delta}",
        "controls": "PASS" if controls_ok else "FAIL",
        "overlay_png": _repo_relative(overlay_grab_path),
        "desktop_png": _repo_relative(screen_grab_path),
        "result": "PASS" if passed else "FAIL",
    }


def _format_results(results) -> str:
    lines = [
        "| Screen | Name | Geometry | Available | DPR | Overlay frame | Center delta | Top delta | Size delta | Controls | Result |",
        "| --- | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in results:
        lines.append(
            "| {index} | {name} | {geometry} | {available} | {dpr:.2f} | "
            "{frame} | {center_delta:.2f} | {top_delta:.2f} | "
            "{size_delta} | {controls} | {result} |".format(**row)
        )
    return "\n".join(lines)


def main() -> int:
    if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        print("FAIL: QT_QPA_PLATFORM=offscreen is not valid for this verifier.")
        return 2

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    screens = app.screens()
    if not screens:
        print("FAIL: no QScreen instances reported by Qt.")
        return 2

    overlay = DynamicIslandOverlay()
    results = []
    try:
        for i in range(len(screens)):
            results.append(_verify_screen(app, overlay, i))
    finally:
        overlay.hide()
        app.processEvents()

    table = _format_results(results)
    print(table)
    print()
    print("Evidence PNGs:")
    for row in results:
        print(f"- screen {row['index']} overlay: {row['overlay_png']}")
        print(f"- screen {row['index']} desktop: {row['desktop_png']}")

    summary_path = EVIDENCE_DIR / "overlay-geometry-results.md"
    summary_path.write_text(
        table
        + "\n\nEvidence PNGs:\n"
        + "\n".join(
            f"- screen {row['index']} overlay: {row['overlay_png']}\n"
            f"- screen {row['index']} desktop: {row['desktop_png']}"
            for row in results
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nSummary written to {summary_path}")

    return 0 if all(row["result"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
