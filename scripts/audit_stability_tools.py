"""Read-only48-adapter readiness audit with explicitly supplied real-run proof."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent_tools import ToolRegistry,_SPECS
    from grangerpet.config import SettingsStore
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--gui-dir',type=Path)
    parser.add_argument('--agent-report',type=Path,action='append',default=[])
    args=parser.parse_args()
    live,agent,gui,proof={},{},{},{}
    def observe(snapshot,label,from_gui=False):
        evidence=snapshot.get('evidence',[])+snapshot.get('search',{}).get('results',[])
        inv=snapshot.get('investigation',{})
        called={row.get('tool') for row in inv.get('calls',[]) if isinstance(row,dict)}
        for row in evidence:
            tool=(row.get('provenance') or {}).get('tool')
            if not tool:continue
            live[tool]=True;proof.setdefault(tool,set()).add(label)
            if tool in called:agent[tool]=True
            if from_gui:gui[tool]=True
        for row in inv.get('completed_steps',[]):
            for call in row.get('calls',[]):
                if call.get('status') in ('complete','partial','empty'):
                    name=call.get('tool');live[name]=True
                    if name in called:agent[name]=True
                    if from_gui:gui[name]=True
                    proof.setdefault(name,set()).add(label)
    for path in args.agent_report:
        report=json.loads(path.read_text(encoding='utf-8'))
        if report.get('mock') is not False or not report.get('passed'):raise ValueError('Agent proof must be an actual successful capability test')
        observe(report['result'],path.name)
    if args.gui_dir:
        report=json.loads((args.gui_dir/'report.json').read_text(encoding='utf-8'))
        if report.get('mock') is not False or not report.get('passed'):raise ValueError('GUI proof must be a completed actual-run report')
        for name in ('telegram-live','graph-explain-live','resumed-live','visual-geoint-live','ton-manual'):
            path=args.gui_dir/(name+'.json')
            if path.exists():observe(json.loads(path.read_text(encoding='utf-8')),path.name,True)
    registry=ToolRegistry(SettingsStore().load())
    catalog={row['name']:row for row in registry.catalog()}
    rows=[]
    for spec in _SPECS:
        row=catalog[spec.name]
        rows.append({'id':spec.name,'registered':True,'ready_local':row['available'],
            'state':row['state'],'agent_callable':row['available'],'live_data_verified':bool(live.get(spec.name)),
            'agent_call_verified':bool(agent.get(spec.name)),'gui_verified':bool(gui.get(spec.name)),
            'structured_input':spec.input_schema is not None,'cancellable':True,
            'requires_confirmation':spec.requires_approval,'reason':row['reason'],
            'proof_files':sorted(proof.get(spec.name,[]))})
    result={'registered':len(rows),'ready_local':sum(row['ready_local'] for row in rows),
        'scope':'Current local readiness plus named actual-run proof only. No all48 live/GUI success claim.',
        'adapters':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Аудит48 адаптеров — текущий этап','',
        'Готовность означает возможность локального запуска. Живые данные, вызов агентом и GUI отмечены только по указанным фактическим прогонам. Синтетические unit-тесты в эти столбцы не входят. Непроверенное не считается неработающим. Пустой результат или частичные данные не доказывают полноту источника.','',
        '| Адаптер | Зарегистрирован | Локально готов | Доступен агенту | Реальные данные | Вызван агентом | Проверен в EXE | Состояние |',
        '|---|---|---|---|---|---|---|---|']
    yes=lambda value:'да' if value else 'не проверено'
    for row in rows:
        lines.append('| `'+row['id']+'` | да | '+('да' if row['ready_local'] else 'нет')+' | '+('да' if row['agent_callable'] else 'нет')+' | '+yes(row['live_data_verified'])+' | '+yes(row['agent_call_verified'])+' | '+yes(row['gui_verified'])+' | '+row['state']+' |')
    lines+=['',f"Всего: {len(rows)}; локально готовы: {result['ready_local']}. Прямой inference GeoCLIP/Waypoint внутри `visual_geoint` подтверждает pipeline; это не отдельный вызов каждого зарегистрированного model-адаптера.",'',
        'Ограничения: закрытые/авторизованные источники требуют собственных полномочий и не проверялись чужими сессиями; ключи не печатаются. Встроенный HTTP имеет общий бюджет загрузки, трафик сторонних CLI этим счётчиком не охвачен. Подробнее о сценариях и частичных результатах — `STABILITY_OVERHAUL.md`.','',
        'Идентификаторы фактических файлов доказательства по адаптерам:','']
    for row in rows:
        if row['proof_files']:lines.append('- `'+row['id']+'`: '+', '.join('`'+name+'`' for name in row['proof_files']))
    (ROOT/'docs/STABILITY_TOOLS48.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('registered','ready_local')}))


if __name__=='__main__':main()
