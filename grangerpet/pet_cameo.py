"""One owned, bounded, input-transparent cameo; no timers or application panels."""
from __future__ import annotations
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtWidgets import QWidget
from .scene_art import cameo_frame


class CameoWindow(QWidget):
    def __init__(self,pet):
        super().__init__(pet,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
            Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|
            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setObjectName('PetCameo');self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pet=pet;self.image=QImage();self.signature=None;self.home=None

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
            self.hide();self.signature=None
            if self.home is not None and pet._pressed_at is None:
                if not pet._dragging:pet.move(self.home)
                self.home=None
            return
        if self.home is None:self.home=QPoint(pet.pos())
        box=self.room();size=pet._display_size;pad=pet._padding
        # Positions account for opaque pixels, not the transparent square around
        # each master. Both retain the same scale and baseline inside the dock.
        main_left=pad+round(size*.13);main_right=pad+round(size*.87)
        guest_left=pad+round(size*.235);guest_right=pad+round(size*.765)
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
        self.setFixedSize(pet.size())
        self.move(round(guest+(1-pose.strength)*(-12 if mirror else 12)),pet.y())
        signature=(pose.cameo,pose.frame,round(pose.strength,2),size,mirror)
        if signature!=self.signature:
            frame=cameo_frame(pet.library,pose)
            if mirror:frame=frame.flipped(Qt.Orientation.Horizontal)
            self.image=QImage(pet.size(),QImage.Format.Format_ARGB32_Premultiplied);self.image.fill(Qt.GlobalColor.transparent)
            p=QPainter(self.image);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.setOpacity(pose.strength)
            p.setClipRect(box.translated(-self.x(),-self.y()))
            p.drawImage(QRect(pad,pad,size,size),frame);p.end();self.signature=signature;self.update()
        if not self.isVisible():self.show()

    def paintEvent(self,event):
        p=QPainter(self);p.drawImage(0,0,self.image)

    def reset(self):
        self.hide();self.image=QImage();self.signature=None
        if self.home is not None:self.pet.move(self.home)
        self.home=None
