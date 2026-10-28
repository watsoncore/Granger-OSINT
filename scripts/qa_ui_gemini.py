"""Render the actual Qt interface with labelled fixtures, never a live API.

Default runs offscreen at Qt factors 100/125/150. --native renders Windows
widgets at the current OS DPI; it does not change Windows scaling. The EXE and
actual Gemini request are intentionally separate release checks.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
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
OUT = ROOT / "output/ui-gemini-qa"
FAKE_KEY = "EXPLICIT-UI-FIXTURE-NOT-A-REAL-KEY"
TON = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"
RAW_TON = "0:" + "0" * 64


def protected_hashes():
    files = list((ROOT / "grangerpet/assets").glob("*")) + list((ROOT / "grangerpet/engine").rglob("*.py"))
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file() and "__pycache__" not in path.parts}


def child(native, factor, label):
    if native:
        os.environ.pop("QT_QPA_PLATFORM", None)
    else:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if factor == 1:
        os.environ.pop("QT_SCALE_FACTOR", None)
    else:
        os.environ["QT_SCALE_FACTOR"] = str(factor)
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget
    from grangerpet.ai_keys import DEFAULT_GEMINI_MODEL
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.engine.models import Result, SourceExecution
    from grangerpet.panel import OsintPanel
    from grangerpet.result_view import compact_content
    from grangerpet.theme import STYLE

    folder = OUT / label
    if folder.exists():
        folder = OUT / (label + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    folder.mkdir(parents=True)
    before = protected_hashes()
    report = {"tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": "native Windows Qt" if native else "offscreen Qt",
              "qt_scale_factor": factor, "fixture_content": "ТЕСТОВЫЕ ДАННЫЕ: synthetic UI/source/AI fixtures; no live API or actual account findings",
              "real_api_called": False, "real_credentials_read_or_written": False,
              "checks": [], "captures": [], "protected_before": before}
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    if not native:
        for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    panel = None
    opened, ai_calls = [], []

    def check(name, condition, detail=None):
        report["checks"].append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError(name + (": " + str(detail) if detail is not None else ""))

    def wait(predicate, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate():
                return True
            QTest.qWait(15)
        return False

    def render_visible_rows():
        if not panel.results_view.isVisible() or panel.result_model.rowCount() == 0:
            return
        samples = [0]
        def ready():
            viewport = panel.results_view.viewport()
            image = viewport.grab().toImage()
            samples[0] = sum(min(image.pixelColor(x, y).getRgb()[:3]) > 105
                             for y in range(8, min(image.height(), 160), 2)
                             for x in range(8, max(8, image.width() - 48), 2))
            return panel.results_view.indexAt(QPoint(16, 16)).isValid() and samples[0] > 25
        check("visible_result_text_" + str(len(report["captures"])), wait(ready), {"text_pixel_samples": samples[0]})

    def capture(name, widget=None):
        widget = widget or panel
        app.processEvents()
        if widget is panel:
            render_visible_rows()
        check("capture_" + name, widget.grab().save(str(folder / (name + ".png"))))
        report["captures"].append(name + ".png")

    def critical(widget):
        return widget.isVisible() and panel.rect().contains(widget.mapTo(panel, widget.rect().topLeft())) and panel.rect().contains(widget.mapTo(panel, widget.rect().bottomRight()))

    def geometry_diagnostics():
        data = {}
        for name in ("mode_tabs", "search_page", "chat_widget", "results_stack", "blockchain_overview"):
            widget = getattr(panel, name)
            data[name] = {"size": [widget.width(), widget.height()], "minimum": [widget.minimumWidth(), widget.minimumHeight()],
                          "minimum_hint": [widget.minimumSizeHint().width(), widget.minimumSizeHint().height()],
                          "font_pixel_size": widget.font().pixelSize(), "font_metrics_height": widget.fontMetrics().height()}
        data["window"] = {"size": [panel.width(), panel.height()], "minimum": [panel.minimumWidth(), panel.minimumHeight()],
                          "minimum_hint": [panel.minimumSizeHint().width(), panel.minimumSizeHint().height()],
                          "layout_minimum": [panel.layout().minimumSize().width(), panel.layout().minimumSize().height()],
                          "frame_size": [panel.frameGeometry().width(), panel.frameGeometry().height()],
                          "dpr": panel.devicePixelRatioF(), "qt_handle_size": [panel.windowHandle().width(), panel.windowHandle().height()]}
        if native and sys.platform == "win32":
            # Read only this diagnostic process's own actual client rectangle.
            import ctypes
            from ctypes import wintypes
            rectangle = wintypes.RECT()
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user.GetClientRect.restype = wintypes.BOOL
            if user.GetClientRect(wintypes.HWND(int(panel.winId())), ctypes.byref(rectangle)):
                data["own_native_client_pixels"] = [rectangle.right - rectangle.left, rectangle.bottom - rectangle.top]
        return data

    def begin(text, label, kind="auto"):
        panel.show_search()
        panel._clear_results()
        panel.text.setText(text)
        panel.set_query_kind(kind)
        panel._query = text
        panel._set_phase("completed_empty")
        panel.status.setText("ТЕСТОВЫЕ ДАННЫЕ · " + label)
        panel.checked_label.setText("Проверено: 1")

    def inject(records, label):
        for record in records:
            panel._engine_result(record)
        panel._set_phase("completed")
        panel.status.setText("ТЕСТОВЫЕ ДАННЫЕ · " + label)
        panel.checked_label.setText("Проверено: 1")
        app.processEvents()

    class FakeGemini:
        def __init__(self, *args, **kwargs):
            pass
        def chat(self, model, messages, *, cancel_event=None):
            ai_calls.append({"kind": "explicit-fixture-chat", "model": model, "messages": len(messages)})
            return "ТЕСТОВЫЕ ДАННЫЕ · это ответ локальной подстановки для проверки интерфейса. Совпадение никнеймов не подтверждает общего владельца. Настоящий Gemini API здесь не вызывается."
        def test_connection(self, model=DEFAULT_GEMINI_MODEL, *, cancel_event=None):
            ai_calls.append({"kind": "explicit-fixture-test", "model": model})
            return {"connected": True, "model": model, "text": "ТЕСТОВЫЕ ДАННЫЕ"}

    try:
        with tempfile.TemporaryDirectory(prefix="GrangerPet-UI-fixtures-") as temporary, ExitStack() as stack:
            stack.enter_context(patch("grangerpet.credentials.CredentialsStore.get", return_value=""))
            stack.enter_context(patch("grangerpet.credentials.CredentialsStore.set", side_effect=AssertionError("UI QA cannot write user credentials")))
            stack.enter_context(patch("grangerpet.credentials.CredentialsStore.delete", side_effect=AssertionError("UI QA cannot delete user credentials")))
            stack.enter_context(patch("grangerpet.ai_keys._development_values", return_value={}))
            stack.enter_context(patch("grangerpet.connections.gemini_key_source", return_value="missing"))
            stack.enter_context(patch("grangerpet.connections.resolve_gemini_key", return_value=FAKE_KEY))
            stack.enter_context(patch("grangerpet.chat.resolve_gemini_key", return_value=FAKE_KEY))
            stack.enter_context(patch("grangerpet.chat.GeminiClient", FakeGemini))
            stack.enter_context(patch("grangerpet.connections.GeminiClient", FakeGemini))
            stack.enter_context(patch("grangerpet.settings_dialog.SettingsDialog.refresh_readiness", return_value=None))
            stack.enter_context(patch("grangerpet.engine.controller.SearchController.start", side_effect=AssertionError("Fixture QA cannot start network sources")))
            stack.enter_context(patch("grangerpet.panel.QDesktopServices.openUrl", side_effect=lambda url: opened.append(url.toString()) or True))
            settings = Settings(ai_provider="gemini", gemini_model=DEFAULT_GEMINI_MODEL)
            store = SettingsStore(Path(temporary) / "settings.json")
            panel = OsintPanel(settings, store)
            panel.show()
            app.processEvents()
            report["qt_platform"] = app.platformName()
            report["actual_device_pixel_ratio"] = panel.devicePixelRatioF()
            check("initial_620x610", (panel.width(), panel.height()) == (620, 610), [panel.width(), panel.height()])
            check("minimum_460x420", (panel.minimumWidth(), panel.minimumHeight()) == (460, 420))
            check("frameless_alt_tab_window", bool(panel.windowFlags() & Qt.WindowType.FramelessWindowHint) and bool(panel.windowFlags() & Qt.WindowType.Window))
            check("single_search_field", panel.text.isVisible() and not panel.direction.isVisible())
            check("initial_no_api_call", not ai_calls and not panel.controller.running)
            panel.status.setText("ТЕСТОВЫЕ ДАННЫЕ · пустой поиск")
            capture("A-empty-search")

            begin("qa.fixture@example.org", "проверка email")
            email_records = [Result(f"qa-registration-{service}", "qa.fixture@example.org", "email_check", service,
                description="ТЕСТОВЫЕ ДАННЫЕ · Не реальная проверка регистрации.",
                details={"email": "qa.fixture@example.org", "service_url": url}, status="registration_detected", sources=["Holehe · QA fixture"])
                for service, url in (("duolingo", "https://www.duolingo.com/"), ("diigo", "https://www.diigo.com/"), ("gravatar", "https://gravatar.com/"))]
            inject(email_records, "три сервиса · не реальные регистрации")
            render_visible_rows()
            check("email_three_rows", panel.result_model.rowCount() == 3)
            check("email_three_rows_fit", panel.results_view.visualRect(panel.result_model.index(2, 0)).bottom() < panel.results_view.viewport().height())
            contents = [compact_content(record.to_dict()) for record in email_records]
            check("email_two_line_compact_rows", all(len(value) == 2 for value in contents), contents)
            check("email_not_repeated_in_rows", all("qa.fixture@example.org" not in str(value) for value in contents))
            visible_caveats = [label for label in panel.findChildren(QLabel) if label.isVisible() and "Регистрация не подтверждает личность" in label.text()]
            check("email_one_shared_caveat", len(visible_caveats) == 1)
            before_status = panel.result_model.rowCount()
            panel._source_status(SourceExecution("qa-fixture", "Explicit fixture", "empty", "ТЕСТОВЫЕ ДАННЫЕ · совпадений нет"))
            check("execution_not_result", panel.result_model.rowCount() == before_status)
            panel.status.setText("ТЕСТОВЫЕ ДАННЫЕ · три сервиса · не реальные регистрации")
            capture("B-compact-email-results")
            index = panel.result_model.index(0, 0)
            panel.results_view.setCurrentIndex(index)
            rect = panel.results_view.visualRect(index)
            QTest.mouseClick(panel.results_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.left() + 18, rect.center().y()))
            check("email_details_from_row", wait(lambda: hasattr(panel, "details_dialog") and panel.details_dialog.isVisible()))
            details = panel.details_dialog
            check("email_details_exact_query", details.fields["Проверяемый email"].text() == "qa.fixture@example.org")
            check("email_service_page_not_invented_profile", details.fields["URL источника"].text() == "https://www.duolingo.com/")
            capture("B-email-details", details)
            details.close()
            app.processEvents()

            begin("fixture-user", "публичные профили", "username")
            long_url = "https://example.invalid/qa-fixture/" + "long-path-segment-" * 28
            profiles = [Result("qa-github", "ТЕСТОВЫЕ ДАННЫЕ · example-user", "profile", "github", "https://example.invalid/qa-github/example-user", status="detected"),
                        Result("qa-long", "ТЕСТОВЫЕ ДАННЫЕ · " + "Длинное имя " * 28, "profile", "Example fixture", long_url, status="detected")]
            inject(profiles, "профили и длинные значения · fixtures")
            capture("C-profile-results")
            check("profiles_horizontal_scroll_disabled", panel.results_view.horizontalScrollBar().maximum() == 0)
            panel.results_view.setCurrentIndex(panel.result_model.index(1, 0))
            panel.show_selected_details()
            check("long_details_value_preserved", panel.details_dialog.fields["URL источника"].text() == long_url)
            capture("C-long-profile-details", panel.details_dialog)
            panel.details_dialog.close()
            app.processEvents()
            index = panel.result_model.index(0, 0)
            rect = panel.results_view.visualRect(index)
            action = panel.results_view.itemDelegate().action_rect(rect)
            QTest.mouseClick(panel.results_view.viewport(), Qt.MouseButton.LeftButton, pos=action.center())
            check("inline_source_action_exact_url", opened[-1:] == [profiles[0].url], opened)

            begin(TON, "TON · синтетические факты Gansar")
            facts = [Result("a" * 64, "ТЕСТОВЫЕ ДАННЫЕ · транзакция", "transaction", "Блокчейн · TON", "https://tonviewer.com/transaction/" + "a" * 64,
                        date="2026-10-28T00:00:00+00:00", details={"normalized_address": RAW_TON, "direction": "in", "amount": "1.25", "asset": "TON"}),
                     Result("qa-counterparty", "ТЕСТОВЫЕ ДАННЫЕ · связанный адрес", "relationship", "Блокчейн · TON", "https://tonviewer.com/" + TON,
                        details={"normalized_address": RAW_TON, "address": "0:" + "1" * 64}, status="check"),
                     Result("qa-attribution", "ТЕСТОВЫЕ ДАННЫЕ · метка источника", "label", "Блокчейн · TON", "https://tonviewer.com/" + TON,
                        details={"normalized_address": RAW_TON, "label": "QA synthetic label"}, status="check")]
            inject(facts, "TON · fixtures, не реальные транзакции")
            check("ton_real_type_overview", panel.blockchain_overview.isVisible() and "3" in panel.blockchain_summary.text())
            check("ton_address_full_value", panel.blockchain_address.text() == RAW_TON)
            check("ton_uncertain_excluded_confirmed_count", panel.result_model.confirmed_count == 1)
            check("ton_groups_only_present_types", panel.fact_group.count() >= 3)
            capture("D-ton-structured-results")
            before_tab_records = deepcopy(panel._records)

            panel.open_settings("ИИ")
            settings_dialog = panel.settings_dialog
            check("settings_four_sections", [panel.connections.tabs.tabText(i) for i in range(panel.connections.tabs.count())] == ["Источники", "Авторизация", "ИИ", "Поиск"])
            panel.connections.gemini_key.setText(FAKE_KEY)
            check("key_masked", panel.connections.gemini_key.echoMode() == QLineEdit.EchoMode.Password)
            check("model_id_exact", panel.connections.selected_model() == DEFAULT_GEMINI_MODEL)
            check("no_plaintext_key_json", not store.path.exists())
            panel.connections.ai_status.setText("ТЕСТОВЫЕ ДАННЫЕ · API не вызывался")
            capture("E-F-gemini-settings", settings_dialog)
            settings_dialog.close()
            app.processEvents()
            check("settings_return_preserves_findings", panel._records == before_tab_records)

            panel.show_chat()
            chat = panel.chat_widget
            chat.input.setPlainText("ТЕСТОВЫЕ ДАННЫЕ · Объясни значение совпадения никнеймов.")
            chat.send.click()
            check("chat_uses_explicit_mock_request", wait(lambda: not chat.busy and bool(chat.messages)))
            check("chat_fixture_reply_displayed", "ТЕСТОВЫЕ ДАННЫЕ · это ответ локальной подстановки" in chat.history.toPlainText())
            check("chat_sdk_model_exact", ai_calls[-1].get("model") == DEFAULT_GEMINI_MODEL)
            chat.history.verticalScrollBar().setValue(chat.history.verticalScrollBar().maximum())
            capture("F-hermione-chat-fixture")
            panel.show_search()
            check("chat_return_preserves_findings", panel._records == before_tab_records)

            panel.resize(460, 420)
            app.processEvents()
            report["minimum_geometry_debug"] = geometry_diagnostics()
            check("minimum_actual_geometry", (panel.width(), panel.height()) == (460, 420), [panel.width(), panel.height()])
            check("minimum_search_actions_inside", all(critical(widget) for widget in (panel.text, panel.find, panel.settings_button, panel.close_button, panel.mode_tabs)))
            check("minimum_no_horizontal_overflow", panel.results_view.horizontalScrollBar().maximum() == 0)
            capture("G-minimum-ton-search")
            panel.show_chat()
            check("minimum_chat_send_inside", critical(chat.send) and critical(chat.input))
            check("minimum_chat_history_visible", chat.history.isVisible() and chat.history.height() >= 40, chat.history.height())
            chat.history.verticalScrollBar().setValue(chat.history.verticalScrollBar().maximum())
            capture("G-minimum-chat")
            panel.show_search()
            settings_dialog.resize(460, 420)
            panel.open_settings("ИИ")
            app.processEvents()
            save = panel.connections.save_button
            check("minimum_settings_save_inside", settings_dialog.rect().contains(save.mapTo(settings_dialog, save.rect().bottomRight())))
            check("minimum_settings_no_horizontal_scroll", panel.connections.tabs.currentWidget().horizontalScrollBar().maximum() == 0)
            capture("G-minimum-gemini-settings", settings_dialog)
            settings_dialog.close()
            panel.resize(620, 610)
            app.processEvents()

            begin("fixture-many", "1000 объектов · явные fixtures", "username")
            for index in range(1000):
                panel._engine_result(Result(f"qa-{index}", f"ТЕСТОВЫЕ ДАННЫЕ · Профиль {index}", "profile", "QA fixture", f"https://example.invalid/qa/{index}"))
            panel.status.setText("ТЕСТОВЫЕ ДАННЫЕ · 1000 объектов · проверка виртуализации")
            render_visible_rows()
            check("1000_virtualized_rows", panel.result_model.rowCount() == 1000)
            children = len(panel.results_view.findChildren(QWidget))
            check("no_per_result_widgets", children < 20, children)
            check("1000_count_exact", panel.result_model.confirmed_count == 1000)
            capture("H-1000-virtualized-results")
            panel.results_view.scrollToBottom()
            check("last_virtual_row_reachable", wait(lambda: panel.results_view.visualRect(panel.result_model.index(999, 0)).intersects(panel.results_view.viewport().rect())))
            capture("H-1000-last-results")
            report["mock_ai_calls"] = ai_calls
            report["source_open_boundary"] = opened
            report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if panel is not None:
            panel.shutdown()
            panel.hide()
            panel.deleteLater()
        app.processEvents()
        after = protected_hashes()
        report["protected_after"] = after
        report["protected_files_unchanged"] = before == after
        report["passed"] = report.get("passed", False) and report["protected_files_unchanged"]
        serialized = json.dumps(report, ensure_ascii=False, indent=2)
        if FAKE_KEY in serialized:
            raise AssertionError("Even fixture credentials must not appear in a QA report")
        (folder / "report.json").write_text(serialized + "\n", encoding="utf-8")
        print(json.dumps({"report": str(folder / "report.json"), "passed": report["passed"],
                          "checks": len(report["checks"]), "dpr": report.get("actual_device_pixel_ratio"),
                          "error": report.get("error")}, ensure_ascii=False), flush=True)
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--scales", help="Qt factors; native defaults to actual OS DPI at factor1")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--factor", type=float, default=1)
    parser.add_argument("--label")
    args = parser.parse_args()
    if args.child:
        label = args.label or ("fixtures-native-" if args.native else "fixtures-offscreen-") + str(round(args.factor * 100))
        return child(args.native, args.factor, label)
    scales = args.scales or ("1" if args.native else "1,1.25,1.5")
    outcomes = []
    for factor in [float(value) for value in scales.split(",")]:
        label = args.label or ("fixtures-native-" if args.native else "fixtures-offscreen-") + str(round(factor * 100))
        command = [sys.executable, __file__, "--child", "--factor", str(factor), "--label", label]
        if args.native:
            command.append("--native")
        outcomes.append(subprocess.run(command, cwd=ROOT, timeout=90).returncode == 0)
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
