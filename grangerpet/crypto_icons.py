"""Read-only local artwork, rasterized before crossing the WebEngine boundary.

The user's pack is not redistributed: incomplete provenance and conditional
trademark permissions require a local-only policy. Missing files use UI glyphs.
"""
from functools import lru_cache
from pathlib import Path
import base64
import hashlib
import re
import xml.etree.ElementTree as ET
import sys

FILES = {
    'network:btc': 'bitcoin.svg', 'network:eth': 'ethereum.svg',
    'network:ton': 'ton.svg', 'network:doge': 'dogecoin.svg',
    'network:solana': 'solana.svg', 'network:tron': 'tron.svg',
    'asset:usdt': 'tether.svg', 'platform:telegram': 'telegram.svg',
    'wallet:openmask': 'openmask.png', 'wallet:tonkeeper': 'tonkeeper.svg',
    'service:cryptobot': 'cryptobot.png', 'service:bybit': 'bybit.png',
    'service:xrocket': 'xrocket.png', 'generic:gift': 'gift.svg',
    'generic:badge': 'badge.svg', 'generic:wallet': 'wallet-cards.svg',
    'generic:infrastructure': 'server-cog.svg', 'generic:unknown': 'unknown.svg',
    'generic:document': 'file-badge.svg',
}
ALLOWED = {'svg', 'g', 'path', 'circle', 'ellipse', 'rect', 'line', 'polyline',
           'polygon', 'defs', 'linearGradient', 'radialGradient', 'stop',
           'clipPath', 'title', 'desc', 'metadata', 'style'}


def validate_svg(data):
    if len(data) > 150_000 or re.search(br'<!DOCTYPE|<!ENTITY|<\?xml-stylesheet', data, re.I):
        raise ValueError('SVG exceeds limits or contains an active declaration')
    root = ET.fromstring(data)
    if root.tag.rsplit('}', 1)[-1] != 'svg' or not root.get('viewBox'):
        raise ValueError('SVG requires a viewBox')
    for element in root.iter():
        tag = element.tag.rsplit('}', 1)[-1]
        # Metadata from exported editors can contain RDF; it is never rendered.
        if tag == 'metadata':
            element.clear()
            continue
        if tag not in ALLOWED:
            raise ValueError('Unsupported SVG element: ' + tag)
        for key, value in element.attrib.items():
            attr = key.rsplit('}', 1)[-1].lower()
            if attr.startswith('on') or attr in ('href', 'src') or re.search(r'url\s*\(|@import|expression\s*\(|javascript:', value, re.I):
                raise ValueError('Active or external SVG attribute')
        if tag == 'style' and re.search(r'url\s*\(|@|expression\s*\(|javascript:', element.text or '', re.I):
            raise ValueError('Unsafe SVG CSS')
    return ET.tostring(root, encoding='utf-8')


def display_metadata(image):
    """Classify the rendered copy without erasing or changing source pixels.

    An opaque white rectangle uses a UI fallback. White inside a transparent
    logo stays intact. Dark monochrome art can use the current theme's ink.
    """
    pixels=[(x,y,image.pixelColor(x,y)) for y in range(image.height())
            for x in range(image.width()) if image.pixelColor(x,y).alpha()>32]
    if not pixels:return {'monochrome':False,'opaque_canvas':False}
    monochrome=all(max(c.red(),c.green(),c.blue())-min(c.red(),c.green(),c.blue())<=6
                   and max(c.red(),c.green(),c.blue())<200 for _,_,c in pixels)
    x0=min(x for x,_,_ in pixels);x1=max(x for x,_,_ in pixels)
    y0=min(y for _,y,_ in pixels);y1=max(y for _,y,_ in pixels)
    corners=[image.pixelColor(x,y) for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1))]
    opaque=all(c.alpha()>245 and min(c.red(),c.green(),c.blue())>245 for c in corners)
    return {'monochrome':monochrome,'opaque_canvas':opaque}


@lru_cache(maxsize=64)
def _raster(path_text, modified, size):
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QImageReader
    from PySide6.QtSvg import QSvgRenderer
    path = Path(path_text)
    data = path.read_bytes()
    if len(data) > 256_000:
        raise ValueError('Artwork exceeds byte limit')
    target = QImage(128, 128, QImage.Format.Format_ARGB32_Premultiplied)
    target.fill(Qt.GlobalColor.transparent)
    raster_pixels = None
    if path.suffix == '.svg':
        renderer = QSvgRenderer(QByteArray(validate_svg(data)))
        if not renderer.isValid():
            raise ValueError('Invalid SVG')
        bounds = renderer.viewBoxF()
        if bounds.width() <= 0 or bounds.height() <= 0:
            raise ValueError('Invalid SVG dimensions')
        ratio = min(112 / bounds.width(), 112 / bounds.height())
        w, h = bounds.width() * ratio, bounds.height() * ratio
        painter = QPainter(target)
        renderer.render(painter, QRectF((128-w)/2, (128-h)/2, w, h))
        painter.end()
    else:
        # One supplied .png is actually JPEG; trust checked magic, not its name.
        if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
            raise ValueError('Unsupported raster signature')
        source = QBuffer()
        source.setData(QByteArray(data))
        source.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(source)
        dimensions = reader.size()
        if not 0 < dimensions.width() <= 2048 or not 0 < dimensions.height() <= 2048:
            raise ValueError('Invalid PNG dimensions')
        raster_pixels = max(dimensions.width(), dimensions.height())
        image = reader.read()
        if image.isNull():
            raise ValueError('Invalid raster content')
        image = image.scaled(112, 112, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(target)
        painter.drawImage((128-image.width())//2, (128-image.height())//2, image)
        painter.end()
    out = QByteArray()
    buffer = QBuffer(out)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    target.save(buffer, 'PNG')
    return {'url': 'data:image/png;base64,' + base64.b64encode(bytes(out)).decode('ascii'),
            'sha256': hashlib.sha256(data).hexdigest(), 'local_only': True,
            'raster_pixels': raster_pixels, **display_metadata(target)}


def load_icons(source_root):
    # Shortcuts may start in any working directory and source_root can be empty.
    # Only the explicit tools root and the app's own project root are searched.
    project = Path(sys.executable).resolve().parent.parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    roots = ([Path(source_root)] if source_root else []) + [project]
    pack = next((root / 'crypto_icon' for root in roots if (root / 'crypto_icon').is_dir()), project / 'crypto_icon')
    icons, unavailable = {}, []
    if not pack.is_dir():
        return {'icons': {}, 'unavailable': list(FILES), 'policy': 'local-only'}
    resolved = pack.resolve()
    for key, filename in FILES.items():
        path = pack / filename
        try:
            if not path.is_file() or path.is_symlink() or path.resolve().parent != resolved:
                raise ValueError('Missing or redirected local artwork')
            stat = path.stat()
            icons[key] = _raster(str(path), stat.st_mtime_ns, stat.st_size)
        except (ValueError, OSError, ET.ParseError):
            unavailable.append(key)
    return {'icons': icons, 'unavailable': unavailable, 'policy': 'local-only'}
