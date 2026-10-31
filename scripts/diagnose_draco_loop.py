"""Reproduce the earlier sleeve envelope and ablate real logical rig layers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def historical(module,path):
    raw=subprocess.check_output(['git','show','bf90135:'+path],cwd=ROOT)
    result=types.ModuleType(module);result.__package__='grangerpet';sys.modules[module]=result
    exec(compile(raw,path,'exec'),result.__dict__)
    return result,hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtWidgets import QApplication
    from grangerpet.animation import SpriteLibrary
    from grangerpet.pet_life import LifePose
    from grangerpet.conversation_pose import conversation_pose
    from grangerpet.articulated import HermioneRig,path
    from grangerpet.scene_pose import ActorPose,BookPose
    import grangerpet.guest_rig as guests
    app=QApplication([]);library=SpriteLibrary();rig=guests.GuestRig(library.scenes.cameos['draco'],'draco')
    old_pose,pose_sha=historical('grangerpet._audit_old_pose','grangerpet/scene_pose.py')
    old_art,art_sha=historical('grangerpet._audit_old_art','grangerpet/articulated.py')
    current_arm,current_ik,current_points=HermioneRig.arm,guests.ik,guests.arm_points
    q=6.2/12;life=LifePose('malfoy','',q,q*10,1,0,0,cameo='draco',variant=1)
    raw=json.loads((ROOT/'resources/animation-qa/draco-loop-pose-v1.json').read_text(encoding='utf-8'))['actor']
    raw['book']=BookPose(**raw['book']);actor=ActorPose(**raw);all_layers={'head','torso','arms','hands','legs'}
    actor.grounded=False
    clean_torso=rig.torso
    old_torso=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);old_torso.fill(Qt.GlobalColor.transparent)
    p=QPainter(old_torso);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setClipPath(path([(194,259),(251,248),(286,260),(299,305),(299,354),(337,425),(288,432),(271,412),(223,419),(188,430),(167,410),(184,336)]))
    p.drawImage(0,0,rig.master);p.end()
    def original_joints(a,side,**_):
        s=(181.,285.+a.left_lift) if side<0 else (292.,285.+a.right_lift)
        e,w=old_pose.ik(s,a.left if side<0 else a.right,side);return s,e,w
    rows=[]
    try:
        for revision in ('before-envelope','current'):
            HermioneRig.arm=staticmethod(old_art.HermioneRig.arm if revision=='before-envelope' else current_arm)
            guests.arm_points=original_joints
            rig.torso=old_torso if revision=='before-envelope' else clean_torso
            for label,layers in (('full',all_layers),('no-arms',all_layers-{'arms'}),('arms-only',{'arms'}),
                ('no-torso',all_layers-{'torso'}),('torso-only',{'torso'}),('head-only',{'head'}),('hands-only',{'hands'})):
                image=QImage(512,512,QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
                p=QPainter(image);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
                start=p.transform();rig.draw(p,actor,layers=layers);end=p.transform();p.end()
                name=f'{revision}-{label}.png';image.save(str(args.output/name))
                rows.append({'image':name,'layers':sorted(layers),'transform_restored':start==end,'format':'ARGB32_Premultiplied'})
    finally:HermioneRig.arm=staticmethod(current_arm);guests.ik=current_ik;guests.arm_points=current_points
    sheet=Image.new('RGB',(7*280,2*310),'#ffffff');d=ImageDraw.Draw(sheet)
    for index,row in enumerate(rows):
        im=Image.open(args.output/row['image']).convert('RGBA').resize((260,260),Image.Resampling.LANCZOS)
        x=index%7*280;y=index//7*310;sheet.paste(im,(x+8,y+35),im);d.text((x+5,y+5),row['image'].replace('.png',''),fill='black')
    sheet.save(args.output/'ablation-white.png')
    holes={}
    for revision in ('before-envelope','current'):
        alpha=Image.open(args.output/f'{revision}-arms-only.png').convert('RGBA').getchannel('A').point(lambda a:255 if a>32 else 0)
        ImageDraw.floodfill(alpha,(0,0),128,border=255);holes[revision]=alpha.histogram()[0]
    (args.output/'report.json').write_text(json.dumps({'q':q,'elapsed':q*10,'character':'draco','enclosed_transparent_pixels_in_sleeves':holes,
        'historical_arm_source':'bf90135:grangerpet/articulated.py','historical_arm_sha256':art_sha,
        'historical_ik_sha256':pose_sha,'method':'Actual GuestRig layers; earlier production sleeve/IK functions restored only inside this isolated diagnostic process',
        'native_released_reference':'output/chibi-reconstruction/addendum-released-malfoy',
        'scope':'Released EXE has its older source-sleeve pose. Hollow procedural envelope reproduced from later preview code, not claimed to be frozen into that older EXE.',
        'rows':rows},indent=2),encoding='utf-8')
    print(json.dumps({'renders':len(rows),'transforms_restored':all(r['transform_restored'] for r in rows)}))


if __name__=='__main__':main()
