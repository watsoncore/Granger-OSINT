"""Local wallpaper imports and bounded, downscaled render assets."""
from collections import OrderedDict
from pathlib import Path
from base64 import b64encode
from io import BytesIO

from .appearance import IMAGE_ID, referenced_wallpapers
from .async_reply import DeferredReply
from .canvas_media import local_image
from .geoint.images import AttachmentStore, GeointError, _decode
from .ui_jobs import UiJob


def render_asset(store, identifier, blur, cancel_event=None):
    from PIL import Image, ImageFilter, ImageOps

    with _decode(store.read_bytes(identifier, cancel_event), cancel_event) as decoded:
        image = ImageOps.exif_transpose(decoded)
        try:
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS, reducing_gap=2)
            if blur:
                filtered = image.filter(ImageFilter.GaussianBlur(blur))
                image.close()
                image = filtered
            output = BytesIO()
            image.save(output, 'WEBP', quality=80, method=3)
            return {'url': 'data:image/webp;base64,' + b64encode(output.getvalue()).decode('ascii'),
                    'width': image.width, 'height': image.height}
        finally:
            image.close()


class WallpaperBridge:
    def __init__(self, bridge):
        self.bridge = bridge
        self.job = None
        self.imported = OrderedDict()
        self.cache = OrderedDict()

    def _store(self):
        from .config import data_directory
        from .credentials import open_bytes, protected_path, seal_bytes
        settings = self.bridge.host.store
        root = Path(settings.path).parent if settings else data_directory()
        return AttachmentStore(protected_path(root / 'wallpapers'), seal=seal_bytes, open_sealed=open_bytes)

    def clear(self):
        self.cache.clear()
        self.imported.clear()
        if self.job:
            self.job.cancel()
            self.job.deleteLater()
            self.job = None

    def action(self, action, payload):
        from .credentials import vault_status

        if self.bridge.surface != 'main':
            raise ValueError('Обои доступны в рабочем пространстве.')
        status = vault_status()
        if status['enabled'] and not status['unlocked']:
            raise ValueError('Разблокируйте хранилище для чтения обоев.')
        if self.job:
            raise ValueError('Обработка изображения уже выполняется.')
        if action == 'wallpaper_choose':
            if payload:
                raise ValueError('Выберите локальное изображение через диалог.')
            from PySide6.QtWidgets import QFileDialog

            path, _ = QFileDialog.getOpenFileName(
                self.bridge.host, 'Выбрать обои полотна', '', 'Изображения (*.png *.jpg *.jpeg *.webp)')
            if not path:
                return None
            store = self._store()

            def task():
                data, _ = local_image(path)
                image = store.import_bytes(data, 'Обои', job.cancelled)
                return {'id': image['id']}

            cache_key = None
        elif action == 'wallpaper_preview':
            identifier, blur = payload.get('id'), payload.get('blur', 0)
            if (set(payload) - {'id', 'blur'} or not isinstance(identifier, str) or not IMAGE_ID.fullmatch(identifier)
                    or type(blur) is not int or not 0 <= blur <= 20):
                raise ValueError('Некорректный запрос предпросмотра обоев.')
            allowed = referenced_wallpapers(self.bridge.host.settings.workspace_appearance)
            if identifier not in allowed and identifier not in self.imported:
                raise ValueError('Изображение не зарегистрировано как обои.')
            cache_key = (identifier, blur)
            if cache_key in self.cache:
                self.cache.move_to_end(cache_key)
                return self.cache[cache_key]
            store = self._store()

            def task():
                return render_asset(store, identifier, blur, job.cancelled)
        else:
            raise ValueError('Неизвестное действие с обоями.')

        reply = DeferredReply()

        def safe_task():
            try:
                return task(), ''
            except GeointError as error:
                return None, str(error)
            except Exception:
                return None, 'Не удалось обработать локальное изображение.'

        job = UiJob(safe_task, self.bridge)
        self.job = job

        def done(result, error):
            if self.job is not job:
                return
            self.job = None
            value, message = result or (None, 'Не удалось обработать локальное изображение.')
            if value and cache_key is None:
                self.imported[value['id']] = None
                self.imported.move_to_end(value['id'])
                while len(self.imported) > 8:
                    self.imported.popitem(last=False)
            elif value:
                self.cache[cache_key] = value
                while len(self.cache) > 4:
                    self.cache.popitem(last=False)
            reply.resolve(value, {'code': 'wallpaper_unavailable', 'error': message} if message else None)
            job.deleteLater()

        job.done.connect(done)
        job.start()
        return reply
