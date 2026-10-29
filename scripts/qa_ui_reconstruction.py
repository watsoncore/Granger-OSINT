"""Source UI integration checks using production Qt/WebChannel/React surfaces.

All messages/evidence are explicitly synthetic UI fixtures. No external API is
called and the user's profile is never opened. Captures only these Qt widgets.
This does not substitute for the final packaged EXE or physical DPI checks.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit('Previous evidence preserved; choose a new output path')
    out.mkdir(parents=True)
    os.environ['APPDATA'] = str(out / 'appdata')
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from grangerpet.desktop_surface import register_desktop_scheme
    from grangerpet.config import Settings, SettingsStore
    from grangerpet.panel import OsintPanel
    from grangerpet.launcher import Launcher
    from grangerpet.theme import apply_theme
    from grangerpet.typography import apply_app_font
    from grangerpet.agent_evidence import normalize_evidence
    register_desktop_scheme()
    started = time.perf_counter()
    app = QApplication([])
    app.setProperty('web_desktop', True)
    apply_app_font(app)
    apply_theme(app, 'dark')
    store = SettingsStore(out / 'appdata' / 'GrangerPet' / 'settings.json')
    settings = Settings(ai_provider='none', reduced_motion=True)
    store.save(settings)
    panel = OsintPanel(settings, store)
    panel.resize(1280, 760)
    panel.show()
    surface = panel.desktop_surface
    bridge = surface.bridge
    checks = []
    metrics = {}

    def wait(predicate, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(30)
        raise TimeoutError('Own source UI did not settle')

    def settle(ms=600):
        QTest.qWait(ms)
        app.processEvents()

    def js(script, target=surface):
        result = []
        target.page().runJavaScript(script, lambda value: result.append(value))
        wait(lambda: bool(result))
        return result[0]

    def check(name, passed, **data):
        checks.append(dict(name=name, passed=bool(passed), **data))

    def capture(name, widget=panel):
        check('screenshot_' + name, widget.grab().save(str(out / (name + '.png'))))

    def route(name):
        bridge.dispatch('route', {'route': name})
        bridge.publish(force=True)
        settle(600)

    def theme(name):
        panel.settings.ui_theme = name
        bridge.publish(force=True)
        apply_theme(app, name)
        settle()

    def dom():
        return json.loads(js('''JSON.stringify((()=>{
          const rect=(selector)=>{const node=document.querySelector(selector);if(!node)return null;const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
          return {theme:document.documentElement.dataset.theme,overflow:document.documentElement.scrollWidth>innerWidth,
          font:document.fonts.check('500 15px Manrope','Гермиона'),width:innerWidth,height:innerHeight,
          dock:rect('.companion-stage'),composer:rect('.composer-zone'),sidebar:rect('.hermione-sidebar'),
          restore:!!document.querySelector('[aria-label="Показать Гермиону и источники"]'),
          mountedMessages:document.querySelectorAll('[data-message-id]').length,mountedSources:document.querySelectorAll('[data-source-id]').length,
          closeSvg:!!document.querySelector('.window-close svg'),cards:[...document.querySelectorAll('.catalog-tool')].map(node=>{const r=node.getBoundingClientRect(),a=node.querySelector('.catalog-tool-actions').getBoundingClientRect();return {top:r.top,bottom:r.bottom,actions:a.top}})};
        })())'''))

    try:
        wait(lambda: bridge.ui_ready)
        metrics['workspace_first_render_ms'] = round((time.perf_counter() - started) * 1000, 2)
        # Explicit fixture data, never stored or described as a live investigation.
        evidence = [normalize_evidence({'type': 'web', 'platform': 'UI fixture only', 'title': f'UI FIXTURE · Источник {index}', 'url': f'https://example.org/ui-fixture/{index}',
            'status': 'read' if index % 3 == 0 else 'failed' if index % 3 == 1 else 'indexed',
            'details': {'text': 'Синтетическая выдержка для проверки интерфейса. Не OSINT-результат.'} if index % 3 == 0 else {}},
            'ui_fixture', 'synthetic source fixture') for index in range(120)]
        panel.chat_widget._last_investigation = {'id': 'ui-fixture-not-live', 'evidence': evidence, 'executions': [], 'status': 'completed'}
        panel.chat_widget.messages = [{'id': f'ui-fixture-{index}', 'role': 'model' if index % 2 else 'user',
            'text': f'UI FIXTURE {index} · Проверка русского текста, длинного URL https://example.org/' + 'path/' * 30,
            'evidence_ids': [record['evidence_id'] for record in evidence] if index == 999 else []} for index in range(1000)]
        bridge.publish(force=True)
        route('chat')
        for name in ('dark', 'black', 'light', 'mono'):
            theme(name)
            current = dom()
            check('chat_theme_' + name, current['theme'] == name and current['font'] and not current['overflow'], dom=current)
            check('bounded_chat_and_sources_' + name, 0 < current['mountedMessages'] < 50 and 0 < current['mountedSources'] < 30)
            capture(name + '-chat')
            route('search')
            current = dom()
            cards = current['cards']
            rows = {}
            for card in cards:
                rows.setdefault(round(card['top']), []).append(card)
            aligned = all(max(c['actions'] for c in row) - min(c['actions'] for c in row) < 2 for row in rows.values())
            check('aligned_cards_' + name, aligned and not current['overflow'], cards=len(cards))
            capture(name + '-tools')
            route('chat')
        for width, height in ((1920,1080),(1600,900),(1366,768),(1280,720),(760,560)):
            panel.resize(width, height)
            for zoom in (.8, 1, 1.25, 1.5):
                surface.setZoomFactor(zoom)
                settle(250)
                current = dom()
                dock = current['dock']
                check(f'layout_{width}x{height}_{zoom}', not current['overflow'] and (current['restore'] or dock and dock['width'] > 0 and dock['height'] >= 130 and dock['right'] <= current['width'] + 1), dom=current)
                if (width, zoom) in ((1366,1.5),(760,1),(1280,1.25)):
                    capture(f'layout-{width}-{zoom}')
        panel.resize(1280,760)
        surface.setZoomFactor(1)
        # A collapsed right pane always has an explicit restoration control.
        js("document.querySelector('[aria-label=\"Показать Гермиону и источники\"]')?.click()")
        settle()
        check('right_pane_restored', dom()['dock'] is not None)
        launcher = Launcher(store)
        launcher.show()
        wait(lambda: launcher.desktop_surface.bridge.ui_ready)
        for name in ('dark','black','light','mono'):
            launcher.settings.ui_theme = name
            launcher.desktop_surface.bridge.publish(force=True)
            settle()
            capture(name + '-launcher', launcher)
            value = js("JSON.stringify({theme:document.documentElement.dataset.theme,icon:!!document.querySelector('.window-close svg'),overflow:document.documentElement.scrollWidth>innerWidth,duplicates:document.querySelectorAll('.launcher-character-stage img').length})", launcher.desktop_surface)
            current = json.loads(value)
            check('launcher_' + name, current['theme'] == name and current['icon'] and not current['overflow'] and current['duplicates'] == 1, dom=current)
        launcher.poll_timer.stop()
        launcher.desktop_surface.shutdown()
        launcher.close()
    finally:
        surface.shutdown()
        panel.shutdown()
        panel.close()
        app.processEvents()
        report = {'method': 'Production source OsintPanel + Launcher, QtWebEngine, WebChannel and built React. Synthetic UI fixtures only; no live API requests. Window dimensions and WebEngine zoom; Windows scaling unchanged.',
            'metrics': metrics, 'checks': checks, 'passed': bool(checks) and all(row['passed'] for row in checks)}
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'checks': len(checks), 'passed': report['passed'], 'output': str(out)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
