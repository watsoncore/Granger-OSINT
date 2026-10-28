"""Exercise the real Qt search UI using explicitly labelled synthetic fixtures.

No service credentials or live networks are used. Native mode renders actual
Windows widgets; optional scale factors simulate Qt layout scaling rather than
changing the user's Windows DPI preference. EXE/SendInput checks are separate.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "search-overhaul-qa"


def _assets():
    folder = ROOT / "grangerpet" / "assets"
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.glob("*") if path.is_file()}


def _child(native: bool, factor: float, label: str) -> int:
    if native:
        os.environ.pop("QT_QPA_PLATFORM", None)
    else:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if factor != 1:
        os.environ["QT_SCALE_FACTOR"] = str(factor)
    else:
        os.environ.pop("QT_SCALE_FACTOR", None)
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.engine.models import Result, SourceStatus
    from grangerpet.panel import OsintPanel
    from grangerpet.theme import STYLE

    OUT.mkdir(parents=True, exist_ok=True)
    folder = OUT / label
    folder.mkdir(exist_ok=True)
    before = _assets()
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "native Windows Qt" if native else "offscreen Qt",
              "scale_factor": factor,
              "content": "Explicit synthetic UI fixtures; not live OSINT results",
              "checks": [], "asset_sha256_before": before}
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if not native:
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name))
    app.setFont(QFont("Segoe UI", 10))
    panel = None

    def check(name, condition, details=""):
        report["checks"].append({"name": name, "passed": bool(condition), "details": details})
        if not condition:
            raise AssertionError(name + ": " + details)

    def capture(name):
        app.processEvents()
        # Batched QListView layout intentionally yields to the event loop. A
        # fixed 40ms snapshot can catch its cleared viewport between batches,
        # even though 1000 records already exist. Require actual visible text,
        # rather than accepting a counter/model count as proof of rendering.
        if panel.result_model.rowCount() and panel.results_view.isVisible():
            deadline = time.monotonic() + 3
            rendered = False
            while time.monotonic() < deadline:
                QTest.qWait(20)
                image = panel.results_view.viewport().grab().toImage()
                text_pixels = sum(
                    min(image.pixelColor(x, y).getRgb()[:3]) > 95
                    for y in range(6, min(image.height(), 150), 2)
                    for x in range(8, max(8, image.width() - 8), 2))
                rendered = panel.results_view.indexAt(QPoint(16, 16)).isValid() and text_pixels > 25
                if rendered:
                    break
            check("rendered_content_" + name, rendered, f"visible text samples: {text_pixels}")
        else:
            QTest.qWait(40)
        path = folder / (name + ".png")
        check("capture_" + name, panel.grab().save(str(path)), str(path.relative_to(ROOT)))

    def fixture(index, *, long=False):
        identifier = f"qa-fixture-{index}"
        return Result.from_dict({
            "id": identifier, "title": "ТЕСТОВЫЕ ДАННЫЕ · " + ("Длинное название " * 16 if long else f"Профиль {index}"),
            "type": "profile", "platform": "QA fixture", "url": "https://example.invalid/" + identifier + ("/" + "a" * 220 if long else ""),
            "description": "Явно тестовое содержимое интерфейса. Не найденный аккаунт и не результат живого поиска.",
            "status": "verified", "sources": ["qa-fixture"]})

    try:
        # Isolate vault reads for this diagnostic process. No key is copied or
        # changed, and no auth-dependent worker is started by these fixtures.
        with tempfile.TemporaryDirectory(prefix="GrangerPet-UI-QA-") as temporary, ExitStack() as stack:
            stack.enter_context(patch("grangerpet.credentials.CredentialsStore.get", return_value=""))
            panel = OsintPanel(Settings(), SettingsStore(Path(temporary) / "settings.json"))
            panel.setWindowTitle("GrangerPet · QA · ТЕСТОВЫЕ ДАННЫЕ")
            panel.show()
            app.processEvents()
            report["qt_platform"] = app.platformName()
            report["device_pixel_ratio"] = panel.devicePixelRatioF()
            check("initial_geometry", panel.width() >= 580 and panel.height() >= 600,
                  f"{panel.width()}x{panel.height()}")
            check("resizable_minimum", panel.minimumWidth() <= 480 and panel.minimumHeight() <= 450)
            check("virtualized_list", hasattr(panel, "results_view") and hasattr(panel, "result_model"))
            check("one_primary_action", panel.find.isVisible() and panel.find.text() == "Найти")
            main_fields = [field.objectName() for field in panel.findChildren(QLineEdit)
                           if field.isVisible() and field.window() is panel]
            check("no_visible_auth_form_in_main", len(main_fields) <= 2, str(main_fields))
            panel._set_phase("completed_empty")
            panel.status.setText("QA · пустая выдача · ТЕСТОВЫЕ ДАННЫЕ")
            capture("initial-empty")
            panel.text.setText("solvnox")
            app.processEvents()
            QTest.qWait(80)
            check("plain_text_needs_clarification", panel.phase == "needs_clarification")
            check("clarification_does_not_start_workers", not panel.controller.running)
            capture("nickname-clarification")
            panel.choose_kind("username")
            app.processEvents()

            # A terminal source status is not an actual result.
            count = panel.result_model.rowCount()
            try:
                panel._engine_result({"source": "qa-fixture", "state": "complete", "message": "завершён"})
            except (ValueError, TypeError):
                pass
            check("execution_is_not_result", panel.result_model.rowCount() == count)
            for index in range(3):
                panel._engine_result(fixture(index, long=index == 1))
            panel._set_phase("completed")
            panel.status.setText("QA · три объекта · ТЕСТОВЫЕ ДАННЫЕ")
            panel._progress(1, 1)
            check("three_actual_rows", panel.result_model.rowCount() == 3 and len(panel._records) == 3)
            capture("three-results")
            panel._source_status(SourceStatus("qa-source", "auth_required",
                "ТЕСТОВЫЕ ДАННЫЕ · сессия не настроена", label="QA тестовый источник"))
            panel._set_phase("completed_with_errors")
            panel.status.setText("QA · неполная проверка · ТЕСТОВЫЕ ДАННЫЕ")
            check("source_error_does_not_add_rows", panel.result_model.rowCount() == 3)
            capture("partial-source-error")
            widget_count = len(panel.findChildren(QWidget))
            for index in range(3, 1000):
                panel._engine_result(fixture(index))
            panel._set_phase("completed")
            panel.status.setText("QA · 1000 объектов · ТЕСТОВЫЕ ДАННЫЕ")
            app.processEvents()
            check("thousand_rows", panel.result_model.rowCount() == 1000)
            check("no_widget_per_result", len(panel.findChildren(QWidget)) - widget_count < 10,
                  f"widget delta {len(panel.findChildren(QWidget)) - widget_count}")
            check("long_values_fit_width", panel.results_view.horizontalScrollBar().maximum() == 0)
            capture("many-results")

            panel.resize(480, 450)
            app.processEvents()
            check("minimum_search_controls_visible", panel.find.isVisible() and panel.rect().contains(panel.find.mapTo(panel, panel.find.rect().center())))
            check("minimum_list_visible", panel.results_view.isVisible() and panel.results_view.height() >= 110,
                  f"viewport logical height {panel.results_view.height()}px; enough for a compact evidence row")
            capture("minimum-size")
            panel.resize(760, 740)
            app.processEvents()
            capture("resized")

            panel.open_settings()
            app.processEvents()
            dialog = panel.settings_dialog
            check("separate_settings_window", dialog.isWindow() and dialog.isVisible())
            secret_fields = [field for field in dialog.findChildren(QLineEdit)
                             if field.echoMode() == QLineEdit.EchoMode.Password]
            check("secret_fields_masked", len(secret_fields) >= 3)
            check("settings_does_not_replace_results", panel.result_model.rowCount() == 1000)
            check("settings_capture", dialog.grab().save(str(folder / "settings.png")))
            if native:
                # This is an offline dependency/import probe, not a service
                # login or OSINT search. Capture the resulting readiness table
                # rather than claiming that its initial empty loading view is
                # evidence of working connections.
                for _ in range(900):
                    if not getattr(dialog, "_jobs", []):
                        break
                    QTest.qWait(50)
                check("readiness_probe_completed", not getattr(dialog, "_jobs", []))
                check("readiness_rows_from_real_probes", dialog.readiness.rowCount() >= 8)
                report["readiness"] = [[dialog.readiness.item(row, col).text()
                                        for col in range(dialog.readiness.columnCount())]
                                       for row in range(dialog.readiness.rowCount())]
                check("settings_readiness_capture", dialog.grab().save(str(folder / "settings-ready.png")))
            dialog.close()
            app.processEvents()
            check("return_from_settings_keeps_results", panel.result_model.rowCount() == 1000)
            panel.result_model.clear()
            ton = "0:" + "a" * 64
            panel.text.setText(ton)
            app.processEvents()
            check("raw_ton_detected_without_manual_selector", "TON" in panel.detection.text())
            observations = [
                {"id": "qa-balance", "title": "ТЕСТОВЫЕ ДАННЫЕ · баланс 12.5 TON", "type": "balance",
                 "platform": "Блокчейн · TON", "url": "https://tonviewer.com/" + ton,
                 "description": "Явный UI fixture: не живая сумма кошелька.",
                 "details": {"network": "TON", "address": ton, "amount": "12.5", "source": "qa-fixture"},
                 "status": "verified", "sources": ["qa-fixture"]},
                {"id": "qa-transaction", "title": "ТЕСТОВЫЕ ДАННЫЕ · " + "b" * 64, "type": "transaction",
                 "platform": "Блокчейн · TON", "url": "https://tonviewer.com/transaction/" + "b" * 64,
                 "description": "Тестовое представление входящего перевода. Не реальная транзакция.",
                 "details": {"direction": "in", "amount": "1.25", "asset": "TON"},
                 "status": "verified", "sources": ["qa-fixture"]},
                {"id": "qa-link", "title": "ТЕСТОВЫЕ ДАННЫЕ · связанный адрес " + ton, "type": "relationship",
                 "platform": "Блокчейн · TON", "url": "https://tonviewer.com/" + ton,
                 "description": "Тестовая наблюдаемая связь; не утверждение об общем владельце.",
                 "details": {"address": ton, "tx_count": 2}, "status": "check", "sources": ["qa-fixture"]},
            ]
            for observation in observations:
                panel._engine_result(observation)
            panel._set_phase("completed")
            panel.status.setText("QA · блокчейн-представление · ТЕСТОВЫЕ ДАННЫЕ")
            check("blockchain_facts_not_deduped_by_explorer_url", panel.result_model.rowCount() == 3)
            check("uncertain_fact_not_counted_as_confirmed", panel.result_model.confirmed_count == 2)
            capture("ton-results-fixture")
            report["passed"] = True
    except Exception as error:
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if panel:
            panel.shutdown()
            if hasattr(panel, "settings_dialog"):
                panel.settings_dialog.hide()
            panel.hide()
            panel.deleteLater()
        app.processEvents()
        report["assets_unchanged"] = before == _assets()
        report["passed"] = report.get("passed", False) and report["assets_unchanged"]
        (folder / "layout-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"label": label, "passed": report["passed"], "error": report.get("error"),
                          "checks": len(report["checks"]), "dpr": report.get("device_pixel_ratio")}))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--scales", default="1,1.25,1.5", help="Qt scale multipliers; native1 uses actual OS DPI")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--factor", type=float, default=1)
    parser.add_argument("--label", default="native")
    args = parser.parse_args()
    if args.child:
        return _child(args.native, args.factor, args.label)
    outcomes = []
    for factor in [float(value) for value in args.scales.split(",")]:
        label = ("native" if args.native else "offscreen") + "-scale-" + str(round(factor * 100))
        command = [sys.executable, __file__, "--child", "--factor", str(factor), "--label", label]
        if args.native:
            command.append("--native")
        result = subprocess.run(command, cwd=ROOT, timeout=60)
        outcomes.append(result.returncode == 0)
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
