"""Native production PetWindow/workspace checks in an isolated empty vault.

Only this process's Qt widgets are captured; panel and native Pet are saved as
separate images because QWidget.grab does not include independent windows.
Large logical viewports are virtual test sizes, not physical monitor claims.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Existing QA evidence preserved; choose another output directory')
    out.mkdir(parents=True)
    os.environ['APPDATA'] = str(out / 'appdata')
    for key in ('DEEPSEEK_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        os.environ.pop(key, None)
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QBitmap, QRegion
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from grangerpet.desktop_surface import register_desktop_scheme
    from grangerpet.config import Settings, SettingsStore
    import grangerpet.credentials as credentials
    from grangerpet.pet import PetWindow
    from grangerpet.theme import apply_theme
    from grangerpet.typography import apply_app_font
    register_desktop_scheme()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setProperty('web_desktop', True)
    apply_app_font(app)
    apply_theme(app, 'dark')
    profile = out / 'appdata' / 'GrangerPet'
    # An empty, uniquely named portable QA vault bypasses real Windows secrets.
    credentials._STORE = credentials.CredentialsStore(prefix='GrangerPet/Character-QA/' + uuid.uuid4().hex,
        directory=profile / 'vault', data_root=profile)
    credentials._STORE.portable.create('synthetic character QA passphrase', secrets={})
    settings = Settings(ai_provider='none', size=195, cursor_reaction=False, reduced_motion=True)
    store = SettingsStore(profile / 'settings.json')
    store.save(settings)
    started = time.perf_counter()
    pet = PetWindow(settings, store)
    panel = pet.panel
    surface = panel.desktop_surface
    pet.show()
    panel.show()
    bridge = surface.bridge
    area = app.primaryScreen().availableGeometry()
    checks = []
    rows = []
    timings = {}

    def check(name, value, **details):
        checks.append({'name': name, 'passed': bool(value), **details})

    def wait(predicate, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(25)
        raise TimeoutError('Own Pet/workspace UI did not settle')

    def settle(ms=600):
        QTest.qWait(ms)
        app.processEvents()
        pet._sync_overlay_placement()
        app.processEvents()

    def js(code):
        result = []
        surface.page().runJavaScript(code, lambda value: result.append(value))
        wait(lambda: bool(result))
        return result[0]

    def activate():
        panel.raise_()
        panel.activateWindow()
        app.processEvents()
        wait(lambda: panel.desktop_window_state()['active'], 5)

    def ensure_open():
        js("document.querySelector('[aria-label=\"Показать Гермиону и источники\"]')?.click()")
        settle()

    def rect(value):
        return [value.x(), value.y(), value.width(), value.height()]

    def capture(name):
        check('capture_panel_' + name, panel.grab().save(str(out / (name + '-workspace.png'))))
        check('capture_pet_' + name, pet.grab().save(str(out / (name + '-pet.png'))))

    def fit_check(name):
        data = json.loads(js('''JSON.stringify((()=>{
          const d=document.querySelector('.companion-stage'),c=document.querySelector('.composer-zone');
          const rect=n=>{if(!n)return null;const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
          return {dock:rect(d),composer:rect(c),restore:!!document.querySelector('[aria-label="Показать Гермиону и источники"]'),
            overflow:document.documentElement.scrollWidth>innerWidth,theme:document.documentElement.dataset.theme,
            viewport:[innerWidth,innerHeight],characterStages:document.querySelectorAll('.companion-stage').length};
        })())'''))
        dock = panel.hermione_dock_geometry()
        sprite = pet.frameGeometry()
        alpha = QRegion(QBitmap.fromImage(pet._rendered.createAlphaMask())).boundingRect()
        model = {'name': name, 'window': rect(panel.geometry()), 'zoom': surface.zoomFactor(),
            'native_dock': rect(dock), 'sprite_window': rect(sprite), 'display_size': pet._display_size,
            'configured_size': pet.settings.size, 'visible': pet.isVisible(), 'suppressed': pet._dock_suppressed,
            'alpha_bounds': rect(alpha), 'dom': data}
        rows.append(model)
        check(name + '_whole_native_sprite_in_actual_dock', bool(not dock.isEmpty() and dock.contains(sprite) and pet.isVisible() and not pet._dock_suppressed), detail=model)
        check(name + '_opaque_head_and_feet_not_clipped', not alpha.isEmpty() and alpha.left() > 0 and alpha.top() > 0 and alpha.right() < pet.width() - 1 and alpha.bottom() < pet.height() - 1)
        check(name + '_desktop_preference_unchanged', pet.settings.size == 195 and store.load().size == 195)
        check(name + '_one_dock_no_horizontal_overflow', data['characterStages'] == 1 and not data['overflow'])
        if data['dock']:
            dom_dock = data['dock']
            zoom = surface.zoomFactor()
            expected = QRect(round(dom_dock['x'] * zoom), round(dom_dock['y'] * zoom), round(dom_dock['width'] * zoom), round(dom_dock['height'] * zoom))
            check(name + '_geometry_tracks_real_zoom', abs(dock.width() - expected.width()) <= 2 and abs(dock.height() - expected.height()) <= 2)
        return model

    try:
        wait(lambda: bridge.ui_ready)
        timings['startup_to_workspace_ready_ms'] = round((time.perf_counter() - started) * 1000, 2)
        bridge.dispatch('route', {'route': 'chat'})
        for width, height in ((1280,720),(1366,768),(1600,900),(1920,1080),(760,560)):
            panel.showNormal()
            panel.resize(width,height)
            # Keep the actual dock on this monitor even for virtual viewports
            # wider than available logical desktop coordinates.
            panel.move(area.right() - panel.width() + 1, area.top())
            activate()
            for zoom in (.8,1,1.25,1.5):
                surface.setZoomFactor(zoom)
                settle()
                ensure_open()
                activate()
                settle()
                name = f'viewport-{width}x{height}-zoom-{zoom}'
                fit_check(name)
                if width in (1280,1366,760) and zoom in (1,1.5):
                    capture(name)
        surface.setZoomFactor(1)
        panel.resize(min(area.width(),1280),min(area.height(),720))
        panel.move(area.right() - panel.width() + 1,area.top())
        activate()
        ensure_open()
        for theme in ('dark','black','light','mono'):
            panel.settings.ui_theme = theme
            apply_theme(app,theme)
            bridge.publish(force=True)
            settle()
            fit_check('theme-' + theme)
            capture('theme-' + theme)
        for mode in ('maximized','windowed'):
            panel.showMaximized() if mode == 'maximized' else panel.showNormal()
            activate()
            settle()
            ensure_open()
            fit_check(mode)
        panel.showMinimized()
        settle()
        check('minimized_restores_desktop_size', pet.settings.size == 195 and pet._display_size == 195 and pet.width() == 219)
        panel.showNormal()
        activate()
        settle()
        ensure_open()
        fit_check('restored-from-minimized')
        js("document.querySelector('[aria-label=\"Свернуть панель Гермионы\"]')?.click()")
        settle()
        check('collapsed_has_explicit_restore_control', bool(js("!!document.querySelector('[aria-label=\"Показать Гермиону и источники\"]')")))
        check('collapsed_has_no_fabricated_dock', panel.hermione_dock_geometry().isEmpty())
        ensure_open()
        fit_check('restored-from-collapse')
        panel.hide()
        settle()
        check('hidden_workspace_restores_configured_desktop_size', pet.settings.size == 195 and pet._display_size == 195 and pet.width() == 219 and pet.isVisible())
        check('cursor_timer_disabled_by_actual_preference', not pet.cursor_timer.isActive())
        check('one_production_pet_window', sum(widget.objectName() == 'DesktopPet' for widget in app.topLevelWidgets()) == 1)
    finally:
        pet.shutdown()
        panel.close()
        app.processEvents()
        report = {'method': 'Production source PetWindow + production workspace/QtWebEngine/WebChannel/built React. Independent native Pet and workspace captured separately. Empty isolated encrypted QA vault; no actual keys and no API calls.',
            'logical_available_screen': rect(area), 'native_dpr': app.primaryScreen().devicePixelRatio(),
            'physical_dpi_settings_changed': False, 'virtual_window_sizes_are_not_physical_monitor_resolutions': True,
            'timings': timings, 'rows': rows, 'checks': checks, 'passed': bool(checks) and all(row['passed'] for row in checks)}
        (out / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'checks':len(checks),'passed':report['passed'],'output':str(out)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
