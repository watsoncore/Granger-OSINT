from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from grangerpet.crypto_icons import display_metadata


def test_opaque_white_canvas_uses_fallback_without_erasing_white_art():
    image=QImage(16,16,QImage.Format.Format_ARGB32)
    image.fill(QColor('white'));image.setPixelColor(8,8,QColor('red'))
    original=bytes(image.constBits())
    assert display_metadata(image)=={'opaque_canvas':True,'monochrome':False}
    assert bytes(image.constBits())==original
    image.fill(Qt.GlobalColor.transparent)
    image.setPixelColor(8,8,QColor('white'));image.setPixelColor(7,8,QColor('blue'))
    assert display_metadata(image)['opaque_canvas'] is False
    assert image.pixelColor(8,8)==QColor('white')


def test_black_transparent_art_can_take_theme_ink():
    image=QImage(16,16,QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    image.setPixelColor(8,8,QColor('black'))
    assert display_metadata(image)=={'opaque_canvas':False,'monochrome':True}
