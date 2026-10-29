"""Theme contrast, actual native SVG rendering and bundled Cyrillic coverage."""
import hashlib
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QColor, QPalette, QRawFont
from PySide6.QtWidgets import QApplication, QWidget

from grangerpet.theme import PALETTES, apply_theme, style_for_theme
from grangerpet.typography import font_family, ui_font
from grangerpet.window_chrome import HeaderControl


def luminance(value):
    rgb = QColor(value).getRgbF()[:3]
    linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in rgb]
    return sum(x * weight for x, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(first, second):
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def test_four_palettes_have_readable_text_and_monochrome_has_no_tint():
    assert set(PALETTES) == {'dark', 'black', 'light', 'mono'}
    for name, palette in PALETTES.items():
        for foreground in ('text', 'secondary', 'muted'):
            for background in ('background', 'surface', 'raised'):
                assert contrast(palette[foreground], palette[background]) >= 4.5, (name, foreground, background)
        assert contrast(palette['accent'], palette['accent_text']) >= 4.5
    for value in PALETTES['mono'].values():
        red, green, blue, _ = QColor(value).getRgb()
        assert red == green == blue
    assert PALETTES['black']['background'] == '#000000'
    assert PALETTES['light']['background'] == '#ffffff'


def test_native_svg_controls_render_in_all_palettes_without_font_glyphs():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    results = {}
    for theme in PALETTES:
        apply_theme(app, theme)
        assert app.palette().color(QPalette.ColorRole.WindowText).name() == PALETTES[theme]['text']
        hashes = []
        for kind in ('close', 'minimize', 'maximize'):
            button = HeaderControl(kind=kind, parent=parent)
            button.show()
            app.processEvents()
            image = button.grab().toImage()
            assert not image.isNull()
            hashes.append(hashlib.sha256(image.constBits()).hexdigest())
            assert button.text() == ''
            button.close()
        assert len(set(hashes)) == 3
        results[theme] = hashes
    assert results['light'] != results['black']
    parent.close()
    apply_theme(app, 'dark')


def test_bundled_native_font_covers_cyrillic_and_real_styles_are_generated():
    app = QApplication.instance() or QApplication([])
    assert font_family() == 'Manrope'
    raw = QRawFont.fromFont(ui_font(15))
    assert raw.isValid()
    assert all(raw.glyphIndexesForString('Гермиона Расследования Источники'))
    assert '#17212b' in style_for_theme('light')
    assert style_for_theme('black') != style_for_theme('light')


def test_secret_dialog_inherits_all_four_palettes_without_a_dark_override():
    from grangerpet.credential_dialog import CredentialDialog
    from PySide6.QtWidgets import QLabel
    app=QApplication.instance() or QApplication([])
    try:
        for theme in PALETTES:
            apply_theme(app,theme)
            dialog=CredentialDialog('deepseek',getter=lambda name:'',setter=lambda *args:None)
            dialog.show();app.processEvents()
            title=dialog.findChildren(QLabel)[0]
            assert 'color:' not in title.styleSheet()
            assert not dialog.styleSheet()
            assert dialog.palette().color(QPalette.ColorRole.WindowText).name()==PALETTES[theme]['text']
            assert not dialog.grab().isNull()
            dialog.reject();dialog.deleteLater();app.processEvents()
    finally:
        apply_theme(app,'dark')
