"""Profile bounded production raster allocations, without WebEngine or user data."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_life import PetLifeController,SCENES
    from grangerpet.pet_actions import action_frame
    from grangerpet.scene_art import cameo_frame
    from perf_process_metrics import _WindowsProcesses
    app=QApplication([]);library=SpriteLibrary();api=_WindowsProcesses()
    clock=[0.];life=PetLifeController(clock=lambda:clock[0]);samples=[];count=0;started=time.perf_counter()
    for cycle in range(10):
        for name,spec in SCENES.items():
            life.finish();life.start_action(name);begin=clock[0]
            for frame in range(100):
                clock[0]=begin+spec.duration*frame/100;pose=life.pose()
                image=action_frame(library,pose)
                guest=cameo_frame(library,pose) if pose.cameo else None
                count+=1
                if count%1000==0:
                    app.processEvents();row=api.counters(os.getpid())
                    samples.append({'frames':count,'private_commit_bytes':row['private_commit_bytes'],'rss_bytes':row['rss_bytes']})
            clock[0]=begin+spec.duration
    report={'frames':count,'elapsed_seconds':round(time.perf_counter()-started,3),
        'samples':samples,'private_commit_growth_after_first_1000':samples[-1]['private_commit_bytes']-samples[0]['private_commit_bytes'],
        'scope':'Actual production QPainter scene_frame/cameo_frame. No WebEngine/native mask/compositor; not a multi-hour application leak proof.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
