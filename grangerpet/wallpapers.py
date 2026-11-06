"""Protected wallpaper originals and viewport-sized render assets."""
from collections import OrderedDict
from pathlib import Path
from base64 import b64encode
from io import BytesIO

from .appearance import IMAGE_ID, referenced_wallpapers
from .async_reply import DeferredReply
from .canvas_media import local_image
from .geoint.images import AttachmentStore, GeointError, MAX_IMAGE_BYTES, _decode
from .ui_jobs import UiJob


def render_asset(store, identifier, blur, cancel_event=None, *, quality='auto', size=None, fit='cover'):
    from PIL import Image, ImageFilter, ImageOps

    original = store.read_bytes(identifier, cancel_event)
    with _decode(original, cancel_event) as decoded:
        mime = {'PNG':'image/png', 'JPEG':'image/jpeg', 'WEBP':'image/webp'}[decoded.format]
        image = ImageOps.exif_transpose(decoded)
        try:
            source_width, source_height = image.size
            full_size = quality == 'original' or fit in ('original', 'center', 'tile')
            if full_size and not blur:
                return {'url':'data:' + mime + ';base64,' + b64encode(original).decode('ascii'),
                        'width':source_width, 'height':source_height,
                        'sourceWidth':source_width, 'sourceHeight':source_height, 'original':True}
            if not full_size:
                edge = 3840 if quality == 'high' else 1920
                if quality == 'auto' and size:
                    ratios = (size[0] / source_width, size[1] / source_height)
                    required = max(image.size) * (min(ratios) if fit == 'contain' else max(ratios))
                    edge = next((value for value in (1920, 2560, 3840) if value >= required), 3840)
                image.thumbnail((edge, edge), Image.Resampling.LANCZOS, reducing_gap=2)
            if blur:
                filtered = image.filter(ImageFilter.GaussianBlur(blur))
                image.close()
                image = filtered
            output = BytesIO()
            profile = image.info.get('icc_profile')
            if image.mode == 'CMYK':
                if profile:
                    from PIL import ImageCms
                    image_rgb = ImageCms.profileToProfile(
                        image, ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile('sRGB'), outputMode='RGB')
                else:
                    image_rgb = image.convert('RGB')
                image.close()
                image = image_rgb
                profile = image.info.get('icc_profile')
            if full_size:
                image.save(output, 'PNG', icc_profile=profile)
                mime = 'image/png'
            else:
                image.save(output, 'WEBP', quality=95, method=3, icc_profile=profile)
                mime = 'image/webp'
            if output.tell() > MAX_IMAGE_BYTES:
                raise ValueError('Изображение для отображения превышает допустимый размер.')
            return {'url': 'data:' + mime + ';base64,' + b64encode(output.getvalue()).decode('ascii'),
                    'width': image.width, 'height': image.height,
                    'sourceWidth':source_width, 'sourceHeight':source_height, 'original':full_size}
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
                self.bridge.host, 'Выбрать обои графа', '', 'Изображения (*.png *.jpg *.jpeg *.webp)')
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
            quality, fit = payload.get('quality', 'auto'), payload.get('fit', 'cover')
            width, height = payload.get('width', 1920), payload.get('height', 1080)
            if (set(payload) - {'id', 'blur', 'quality', 'width', 'height', 'fit'}
                    or not isinstance(identifier, str) or not IMAGE_ID.fullmatch(identifier)
                    or type(blur) is not int or not 0 <= blur <= 20
                    or quality not in ('auto', 'high', 'original')
                    or fit not in ('cover', 'contain', 'center', 'tile', 'stretch', 'original')
                    or any(type(value) is not int or not 1 <= value <= 16384 for value in (width, height))):
                raise ValueError('Некорректный запрос предпросмотра обоев.')
            allowed = referenced_wallpapers(self.bridge.host.settings.workspace_appearance)
            if identifier not in allowed and identifier not in self.imported:
                raise ValueError('Изображение не зарегистрировано как обои.')
            size = (width, height)
            cache_key = (identifier, blur, quality, fit, width, height)
            if cache_key in self.cache:
                self.cache.move_to_end(cache_key)
                return self.cache[cache_key]
            store = self._store()

            def task():
                return render_asset(store, identifier, blur, job.cancelled, quality=quality, size=size, fit=fit)
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
                while len(self.cache) > 1 and (len(self.cache) > 3 or sum(
                        len(asset['url']) + asset['width'] * asset['height'] * 4
                        for asset in self.cache.values()) > 96 * 1024 * 1024):
                    self.cache.popitem(last=False)
            reply.resolve(value, {'code': 'wallpaper_unavailable', 'error': message} if message else None)
            job.deleteLater()

        job.done.connect(done)
        job.start()
        return reply
