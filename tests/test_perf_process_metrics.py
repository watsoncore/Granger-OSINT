"""Counter arithmetic/ancestry fixtures; no windows or other apps are opened."""
from pathlib import Path
import importlib.util


spec=importlib.util.spec_from_file_location('perf_process_metrics',Path(__file__).resolve().parents[1]/'scripts/perf_process_metrics.py')
metrics=importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class ProcessApi:
    def __init__(self,rows):self.rows=rows;self.queried=[]
    def ancestry(self):return {pid:{'parent_pid':r['parent_pid'],'threads':r['threads']} for pid,r in self.rows.items()}
    def counters(self,pid):
        self.queried.append(pid)
        return {k:v for k,v in self.rows[pid].items() if k not in ('parent_pid','threads')}


def row(pid,image,parent=0,birth=1,cpu=1):
    return {'pid':pid,'image':str(Path(image).resolve()),'parent_pid':parent,'threads':3,'creation_ticks':birth,
        'cpu_seconds':cpu,'rss_bytes':400,'private_commit_bytes':200}


def monitor(monkeypatch,rows):
    api=ProcessApi(rows);monkeypatch.setattr(metrics,'_WindowsProcesses',lambda:api)
    return metrics.ProcessSampler(exe=Path('Granger-OSINT.exe'),gpu=False),api


def test_verifies_exact_root_and_ignores_unrelated_process_tree(monkeypatch):
    sampler,api=monitor(monkeypatch,{1:row(1,'Granger-OSINT.exe'),2:row(2,'QtWebEngineProcess.exe',parent=1),
        7:row(7,'unrelated.exe'),8:row(8,'another.exe',parent=7)})
    value=sampler.sample([1])
    assert [r['pid'] for r in value['processes']]==[1,2]
    assert set(api.queried)=={1,2}
    assert value['process_count']==2 and value['thread_count']==6
    assert value['rss_bytes_sum']==800 and value['private_commit_bytes_sum']==400
    assert value['private_working_set_bytes'] is None


def test_rejects_wrong_image_and_its_descendants(monkeypatch):
    sampler,api=monitor(monkeypatch,{7:row(7,'unrelated.exe'),8:row(8,'QtWebEngineProcess.exe',parent=7)})
    value=sampler.sample([7])
    assert value['rejected_root_pids']==[7] and value['process_count']==0
    assert api.queried==[7]


def test_tracks_known_child_after_parent_exit_but_rejects_pid_reuse(monkeypatch):
    sampler,api=monitor(monkeypatch,{1:row(1,'Granger-OSINT.exe'),2:row(2,'worker.exe',parent=1,birth=2)})
    sampler.sample([1]);api.rows.pop(1)
    assert sampler.sample([])['process_count']==1
    api.rows[2]=row(2,'unrelated.exe',birth=9)
    assert sampler.sample([])['process_count']==0


def test_cpu_delta_and_machine_normalization_and_na_summary(monkeypatch):
    sampler,api=monitor(monkeypatch,{1:row(1,'Granger-OSINT.exe',cpu=2)})
    stamps=iter([0,0,0,2,2,2]);monkeypatch.setattr(metrics.time,'monotonic',lambda:next(stamps))
    monkeypatch.setattr(metrics.os,'cpu_count',lambda:4)
    first=sampler.sample([1]);api.rows[1]['cpu_seconds']=3
    second=sampler.sample([1])
    assert first['cpu_percent_one_core'] is None
    assert second['cpu_percent_one_core']==50 and second['cpu_percent_machine']==12.5
    summary=metrics.summarize([first,second])
    assert summary['medians']['cpu_percent_one_core']==50
    assert summary['gpu_medians']['gpu_dedicated_bytes'] is None
