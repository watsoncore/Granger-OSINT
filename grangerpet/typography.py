"""One local system font family and logical pixel sizes for all Qt surfaces."""
from PySide6.QtGui import QFont, QFontDatabase


def font_family():
    families = set(QFontDatabase.families())
    for family in ('Segoe UI Variable', 'Segoe UI Variable Text', 'Segoe UI'):
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

