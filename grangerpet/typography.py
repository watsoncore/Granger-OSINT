"""Bundled Cyrillic Manrope, with system fallback for unbuilt source checkouts."""
from pathlib import Path
import sys
from PySide6.QtGui import QFont, QFontDatabase

_font_checked = False


def font_family():
    global _font_checked
    if not _font_checked:
        root = Path(sys._MEIPASS) / 'frontend' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'frontend' / 'public'
        font_file = root / 'fonts' / 'Manrope-Variable.ttf'
        if font_file.is_file():
            QFontDatabase.addApplicationFont(str(font_file))
        _font_checked = True
    families = set(QFontDatabase.families())
    for family in ('Manrope', 'Segoe UI Variable', 'Segoe UI Variable Text', 'Segoe UI'):
        if family in families:
            return family
    return 'Segoe UI'


def ui_font(size_px=14, weight=QFont.Weight.Normal):
    font = QFont(font_family())
    font.setPixelSize(int(size_px))
    font.setWeight(weight)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def apply_app_font(app, size_px=14):
    app.setFont(ui_font(size_px))

