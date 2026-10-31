"""Cached source layers; all scene rendering delegates to one articulated rig."""
from pathlib import Path
from PySide6.QtGui import QImage


class SceneArtLibrary:
    def __init__(self,directory:Path):
        self.layers={name:QImage(str(directory/f'hermione-{name}.png'))
            for name in ('base','head','body','wand_arm','free_arm','left_leg','right_leg')}
        self.cameos={name:QImage(str(directory/('harry-v2.png' if name=='harry' else f'{name}.png')))
            for name in ('draco','ron','harry')}
        self.hair_repair=QImage(str(directory/'hermione-left-curl-v2.png'))
        self.hair_fringe=QImage(str(directory/'hermione-hair-fringe-v2.png'))
        if any(im.isNull() for im in (*self.layers.values(),*self.cameos.values(),self.hair_repair,self.hair_fringe)):
            raise ValueError('Не удалось прочитать локальные слои сцен персонажа')


def scene_frame(library,pose,*,size=256,dpr=1.):
    from .articulated import render_action
    return render_action(library,pose,size,dpr)


def cameo_frame(library,pose,*,size=256,dpr=1.):
    from .guest_rig import render_guest
    return render_guest(library,pose,size,dpr)
