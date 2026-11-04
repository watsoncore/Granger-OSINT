"""Read-only native viewer; never modifies the protected original image."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPixmap,QPainter
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QGraphicsView,QGraphicsScene


class ZoomImage(QGraphicsView):
    def wheelEvent(self,event):
        factor=1.18 if event.angleDelta().y()>0 else 1/1.18
        scale=self.transform().m11()*factor
        if .02<=scale<=20:self.scale(factor,factor)
        event.accept()


class OriginalImageViewer(QDialog):
    def __init__(self,data,metadata,parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Оригинал · '+metadata.get('name','Изображение'))
        self.resize(1000,760)
        image=QImage.fromData(data)
        if image.isNull():raise ValueError('Исходное изображение не прочитано.')
        scene=QGraphicsScene(self);scene.addPixmap(QPixmap.fromImage(image))
        self.view=ZoomImage(scene,self)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        layout=QVBoxLayout(self);buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (('Вписать',self.fit),('100%',self.view.resetTransform),('+',lambda:self.view.scale(1.25,1.25)),('−',lambda:self.view.scale(.8,.8))):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(QLabel(f"{metadata['width']} × {metadata['height']} · {metadata['bytes']} bytes · {metadata['mime']}"))
        layout.addWidget(self.view)
        layout.addWidget(QLabel('SHA-256: '+metadata['sha256']))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0,self.fit)

    def fit(self):self.view.fitInView(self.view.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
