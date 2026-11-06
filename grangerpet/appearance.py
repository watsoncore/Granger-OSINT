"""Validated local presentation preferences, separate from investigations."""
import json
import re


IMAGE_ID = re.compile(r'img_[0-9a-f]{64}')
CANVAS_ID = re.compile(r'[a-f0-9]{32}')
THEMES = ('dark', 'black', 'light', 'mono', 'azure', 'crimson', 'violet', 'silver', 'amber', 'custom')
WALLPAPERS = ('theme', 'graphite', 'mist', 'smoke', 'depth', 'black', 'grid', 'solid', 'gradient', 'image')
FITS = ('cover', 'contain', 'center', 'stretch', 'tile')
EDGE_STYLES = ('straight', 'curved', 'orthogonal', 'bezier')
MAX_PREFERENCES = 48_000


def _enum(value, choices, default):
    return value if value in choices else default


def _integer(value, low, high, default):
    return min(high, max(low, value)) if type(value) is int else default


def _color(value, default=''):
    return value.lower() if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value) else default


def wallpaper(value):
    data = value if isinstance(value, dict) else {}
    image = data.get('image')
    return {
        'source': _enum(data.get('source'), WALLPAPERS, 'theme'),
        'image': image if isinstance(image, str) and IMAGE_ID.fullmatch(image) else '',
        'fit': _enum(data.get('fit'), FITS, 'cover'),
        'anchor': _enum(data.get('anchor'), ('screen', 'world'), 'screen'),
        'x': _integer(data.get('x'), 0, 100, 50),
        'y': _integer(data.get('y'), 0, 100, 50),
        'scale': _integer(data.get('scale'), 50, 200, 100),
        'dim': _integer(data.get('dim'), 0, 95, 65),
        'blur': _integer(data.get('blur'), 0, 20, 0),
        'opacity': _integer(data.get('opacity'), 0, 100, 100),
        'color': _color(data.get('color'), '#11171f'),
        'end': _color(data.get('end'), '#242335'),
    }


def _preset(value):
    data = value if isinstance(value, dict) else {}
    colors = data.get('colors')
    colors = colors if isinstance(colors, dict) else {}
    return {
        'theme': _enum(data.get('theme'), THEMES, 'dark'),
        'colors': {key: color for key in ('accent', 'node', 'edge', 'hover', 'nav', 'button')
                   if (color := _color(colors.get(key)))},
        'glow': _integer(data.get('glow'), 0, 36, 12),
        'border': _integer(data.get('border'), 30, 100, 75),
        'cardRadius': _integer(data.get('cardRadius'), 0, 24, 12),
        'panelRadius': _integer(data.get('panelRadius'), 0, 30, 16),
        'surface': _integer(data.get('surface'), 75, 100, 96),
        'frost': _integer(data.get('frost'), 0, 18, 8),
        'reflection': _integer(data.get('reflection'), 0, 40, 10),
        'shadow': _integer(data.get('shadow'), 0, 50, 22),
        'density': _enum(data.get('density'), ('compact', 'comfortable'), 'comfortable'),
        'edges': _enum(data.get('edges'), EDGE_STYLES, 'curved'),
        'effects': _enum(data.get('effects'), ('full', 'reduced', 'off'), 'full'),
        'reducedMotion': data.get('reducedMotion') is True,
        'wallpaper': wallpaper(data.get('wallpaper')),
    }


def decode_appearance(value):
    if not isinstance(value, str) or len(value) > MAX_PREFERENCES:
        return {}
    try:
        data = json.loads(value)
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_appearance(value):
    data = decode_appearance(value)
    if not data:
        return ''
    current = _preset(data)
    overrides = data.get('overrides')
    current['overrides'] = {
        key: wallpaper(value) for key, value in list(overrides.items())[:64]
        if CANVAS_ID.fullmatch(key) and isinstance(value, dict)
    } if isinstance(overrides, dict) else {}
    presets = data.get('presets')
    current['presets'] = {}
    if isinstance(presets, dict):
        for name, preset in list(presets.items())[:12]:
            name = name.strip()
            if 0 < len(name) <= 48 and name.isprintable() and isinstance(preset, dict):
                current['presets'][name] = _preset(preset)
    current['hidePrivate'] = data.get('hidePrivate') is not False
    return json.dumps(current, ensure_ascii=False, separators=(',', ':'))


def referenced_wallpapers(value):
    data = decode_appearance(value)
    entries = [data.get('wallpaper'), *data.get('overrides', {}).values(),
               *(item.get('wallpaper') for item in data.get('presets', {}).values())]
    return {entry['image'] for entry in entries if entry and entry.get('image')}
