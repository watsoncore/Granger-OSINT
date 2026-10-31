"""One owned, bounded, input-transparent cameo; no timers or application panels."""
from __future__ import annotations
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtWidgets import QWidget
from .guest_rig import paint_pair
from .scene_pose import track


class CameoWindow(QWidget):
    def __init__(self,pet):
        super().__init__(pet,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|
            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setObjectName('PetCameo');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pet=pet;self.image=QImage();self.signature=None;self.home=None
        self.hero_pose=None;self.includes_hero=True

    def room(self):
        pet=self.pet
        screen=QGuiApplication.screenAt(pet.frameGeometry().center()) or QGuiApplication.primaryScreen()
        return pet._dock_bounds or screen.availableGeometry().adjusted(6,6,-6,-6)

    def available(self):
        box=self.room();size=self.pet._display_size
        # At most 10% of a sprite's outer hair may overlap in a narrow dock.
        # Faces remain apart; transparent square padding does not consume room.
        return size>=80 and box.width()>=size*1.17+8 and box.height()>=size+16

    def update_pose(self,pose):
        pet=self.pet
        if not pose.cameo or pet._ending or pet._dock_suppressed or not pet.isVisible() or not self.available() or pet._pressed_at is not None:
            self.hide();self.signature=None;self.hero_pose=None
            if self.home is not None and pet._pressed_at is None:
                if not pet._dragging:pet.move(self.home)
                self.home=None
            return
        if self.home is None:self.home=QPoint(pet.pos())
        box=self.room();size=pet._display_size;pad=pet._padding
        # Positions account for opaque pixels, not the transparent square around
        # each master. Both retain the same scale and baseline inside the dock.
        main_left=pad+round(size*.09);main_right=pad+round(size*.91)
        guest_left=pad+round(size*.21);guest_right=pad+round(size*.80)
        overlap=max(0,main_right-main_left+guest_right-guest_left+16-box.width())
        right_main=box.right()-main_right-4
        left_main=box.left()-main_left+4
        target=max(left_main,min(self.home.x()+size*.28,right_main))
        guest=target+main_left-guest_right-8+overlap
        mirror=True
        if guest+guest_left<box.left()+4:
            target=max(left_main,min(self.home.x()-size*.28,right_main))
            guest=target+main_right-guest_left+8-overlap;mirror=False
        if guest+guest_left<box.left() or guest+guest_right>box.right():
            self.hide();return
        pet.move(round(self.home.x()+(target-self.home.x())*pose.strength),self.home.y())
        # One input-transparent stage owns BOTH drawings and the single note.
        # The pet keeps its independent native hit region underneath this stage.
        walk=1-track(pose.progress,(0.,0.),(.16,1.),(.84,1.),(1.,0.))
        guest_x=round(guest+walk*(-40 if mirror else 40))
        guest_x=max(box.left()-guest_left+4,min(guest_x,box.right()-guest_right-4))
        left=round(min(self.home.x(),target,guest-42));right=round(max(self.home.x(),target,guest+42)+pet.width())
        self.setGeometry(QRect(left,pet.y(),right-left,pet.height()))
        dpr=pet.devicePixelRatioF()
        signature=(pose.cameo,pose.variant,pose.frame,size,mirror,pet.x(),guest_x,dpr)
        if signature!=self.signature:
            self.image=QImage(round(self.width()*dpr),round(self.height()*dpr),QImage.Format.Format_ARGB32_Premultiplied)
            self.image.setDevicePixelRatio(dpr);self.image.fill(Qt.GlobalColor.transparent)
            p=QPainter(self.image);p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
            p.setClipRect(box.translated(-self.x(),-self.y()))
            p.translate(pet.x()-self.x()+pad,pad);p.scale(size/512,size/512)
            scene=paint_pair(p,pet.library,pose,(guest_x-pet.x())*512/size,mirror)
            self.hero_pose=scene.hero;p.end();self.signature=signature;self.update()
        if not self.isVisible():self.show()

    def paintEvent(self,event):
        p=QPainter(self);p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(),Qt.GlobalColor.transparent);p.drawImage(0,0,self.image)

    def reset(self):
        self.hide();self.image=QImage();self.signature=None;self.hero_pose=None
        if self.home is not None:self.pet.move(self.home)
        self.home=None
