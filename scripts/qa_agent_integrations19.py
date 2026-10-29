"""A bounded real DeepSeek/registry test; never reads user chats or sends pixels."""
import argparse
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent import AgentRunner,AgentLimits
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.ai import DeepSeekClient
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    from grangerpet.config import Settings
    from grangerpet.geoint import AttachmentStore
    from grangerpet.credentials import CredentialsStore
    from grangerpet.visual_models.manager import get_manager
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scenario',choices=('visual','public'),default='visual');args=p.parse_args()
    if args.output.exists():raise SystemExit('Previous paid API evidence preserved')
    key=resolve_deepseek_key()
    if not key:raise SystemExit('No saved model credential; real agent test not executed')
    store=AttachmentStore(ROOT/'output/integrations19/agent-attachments',seal=lambda b:CredentialsStore._protect(b),
                          open_sealed=lambda b:CredentialsStore._protect(b,decrypt=True))
    image=store.import_bytes((ROOT/'output/integrations19/visual-photos/moscow-no-gps.jpg').read_bytes(),'test-no-gps.jpg')
    allowed_names={'visual_geoint','evidence_graph'} if args.scenario=='visual' else {'shadow_regions','mail_dns','x_profile','arctic_posts','map_panoramax'}
    class Scope(ToolRegistry):
        allowed=allowed_names
        def catalog(self,**kwargs):return [r for r in super().catalog(**kwargs) if r['name'] in self.allowed]
        def schemas(self,*,task=None,**kwargs):return [r for r in super().schemas(task=task,**kwargs) if r['function']['name'] in self.allowed]
        def execute(self,name,*a,**kw):
            if name not in self.allowed:raise ValueError('Outside QA scope')
            return super().execute(name,*a,**kw)
    reg=Scope(Settings(),secret_getter=lambda _: '',image_store=store,attachment_ids=[image['id']],redactions=(key,))
    runner=AgentRunner(DeepSeekClient(key),reg,limits=AgentLimits(max_steps=6,max_tool_calls=7,max_tokens=60000,timeout=300,per_tool_timeout=240))
    checkpoints=[]
    try:
        goal=('Определи возможное место съёмки выбранного изображения '+image['id']+'. GPS отсутствует. Выполни visual_geoint с двумя моделями, затем evidence_graph по фото и кандидатам. Краткий итог по-русски: полученные кандидаты и ограничения. Raw score не вероятность; независимую проверку картами не выдумывай.' if args.scenario=='visual' else
            'Выполни пять небольших реальных проверок доступными инструментами: DNS email contact@example.org (не проверять существование ящика); публичный профиль X jack; одну архивную Reddit-публикацию subreddit python; геометрические полосы ShadowFinder при object_height10 shadow_length5 datetime_utc2024-02-29T13:59:59Z max_cells10; GEOINT Panoramax рядом latitude48.8584 longitude2.2945 limit1. Затем краткий итог по-русски с ограничениями, без вывода сырых JSON. Ничью личность не устанавливать, активных сканирований не выполнять.')
        result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':goal}],
            cancel_event=threading.Event(),checkpoint_callback=checkpoints.append)
        report={'mock':False,'model':DEFAULT_DEEPSEEK_MODEL,'images_sent_to_model':False,'user_history_read':False,
            'private_source_keys_used':False,'result':result,'checkpoint_count':len(checkpoints)}
        observed={e.get('provenance',{}).get('tool') for e in result.get('evidence',[])}
        completed_tools={e.get('tool') for e in result['investigation'].get('executions',[]) if e.get('status') in ('complete','completed','empty')}
        report['scenario']=args.scenario
        report['all_tools_returned_evidence']=allowed_names <= observed
        report['passed']=(result['investigation']['status']=='completed' and
            (allowed_names <= completed_tools if args.scenario=='public' else
             any(e.get('provenance',{}).get('tool')=='visual_geoint' and e.get('details',{}).get('predictions') for e in result.get('evidence',[])) and 'evidence_graph' in observed))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'status':result['investigation']['status'],'evidence':len(result.get('evidence',[]))}))
        return 0 if report['passed'] else 1
    finally:get_manager().close()


if __name__=='__main__':raise SystemExit(main())
