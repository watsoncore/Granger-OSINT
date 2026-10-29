"""Actual DeepSeek coordination over public sources without source API keys."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from grangerpet.agent import AgentLimits,AgentRunner
    from grangerpet.agent_tools import ToolRegistry
    from grangerpet.ai import DeepSeekClient,AIError
    from grangerpet.ai_keys import resolve_deepseek_key,DEFAULT_DEEPSEEK_MODEL
    from grangerpet.config import Settings
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise SystemExit('Existing paid-call evidence preserved')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    key=resolve_deepseek_key()
    report={'tested_at_utc':datetime.now(timezone.utc).isoformat(),'mock':False,'personal_source_keys_used':False,
        'model_key_available':bool(key),'model':DEFAULT_DEEPSEEK_MODEL,'user_history_read':False,'events':[],'passed':False}
    if not key:
        report['status']='not_executed_no_saved_model_key'
    else:
        class PublicScope(ToolRegistry):
            allowed=frozenset(('github_profile','github_users','github_repositories','hn_search','hn_profile','openlibrary_search','wikipedia_search','web_read','web_search'))
            def catalog(self,**kwargs):return [r for r in super().catalog(**kwargs) if r['name'] in self.allowed]
            def schemas(self,**kwargs):return [r for r in super().schemas(**kwargs) if r['function']['name'] in self.allowed]
            def execute(self,name,*a,**k):
                if name not in self.allowed:raise ValueError('Outside public QA scope')
                return super().execute(name,*a,**k)
        registry=PublicScope(Settings(),secret_getter=lambda name:'',redactions=(key,))
        runner=AgentRunner(DeepSeekClient(key),registry,limits=AgentLimits(max_steps=4,max_tool_calls=5,timeout=120,max_tokens=12000))
        checkpoints=[]
        try:
            result=runner.run(DEFAULT_DEEPSEEK_MODEL,[{'role':'user','text':'Найди публичные сведения об аккаунте octocat на GitHub. Получи настоящую публичную запись, сообщи имя и число публичных репозиториев, если источник их возвращает. Укажи ссылку и ограничение: совпадение никнейма не устанавливает общую личность. Другие персональные подключения не настроены; используй доступные публичные источники. Кратко по-русски.'}],cancel_event=threading.Event(),checkpoint_callback=lambda value:checkpoints.append(value),on_event=lambda e:report['events'].append({k:e[k] for k in ('type','tool','status','step','count') if k in e}))
            evidence=result.get('evidence',[])
            report.update(status=result['investigation']['status'],result=result,checkpoint_count=len(checkpoints),checkpoint_has_evidence=bool(checkpoints and checkpoints[-1].get('evidence')))
            report['passed']=result['investigation']['status']=='completed' and bool(evidence) and any(r.get('provenance',{}).get('tool')=='github_profile' and isinstance(r.get('details',{}).get('public_repos'),int) for r in evidence) and bool(result.get('text'))
        except AIError as exc:report.update(status='api_error',error_code=exc.code)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('status','passed','checkpoint_count','checkpoint_has_evidence')},ensure_ascii=True))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
