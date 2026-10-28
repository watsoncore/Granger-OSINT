"""Virtualized evidence rows: executions cannot be inserted as search results."""
from __future__ import annotations

from urllib.parse import urlsplit

from PySide6.QtCore import QAbstractListModel, QEvent, QModelIndex, QPointF, QRect, QSize, Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyle

from .engine.models import Result, result_key, is_confirmed
from .typography import ui_font
from .motion import reduced_motion


BLOCKCHAIN_TYPES = {"balance", "transaction", "asset", "label", "relationship", "address", "attribution"}
TYPE_NAMES = {"profile": "Публичный профиль", "web": "Веб-страница", "snapshot": "Архивный снимок",
              "web_snapshot": "Архивный снимок", "archive": "Архивный снимок", "post": "Публикация",
              "channel": "Публичный канал", "balance": "Баланс", "transaction": "Транзакция",
              "asset": "Актив", "label": "Атрибуция источника", "relationship": "Связанный адрес",
              "phone_metadata": "Сведения о формате номера", "email_check": "Проверка email"}

SERVICE_NAMES = {"github": "GitHub", "gitlab": "GitLab", "youtube": "YouTube", "tiktok": "TikTok",
                 "telegram": "Telegram", "vk": "ВКонтакте", "vkontakte": "ВКонтакте", "instagram": "Instagram",
                 "duolingo": "Duolingo", "diigo": "Diigo", "gravatar": "Gravatar", "holehe": "Holehe"}


def service_name(value):
    text = str(value or "")
    return SERVICE_NAMES.get(text.casefold().replace(" ", ""), text[:1].upper() + text[1:])


def source_url(value):
    """A registration service page is a source, never an invented profile URL."""
    address = value.get("url") or (value.get("details") or {}).get("service_url") or ""
    try:
        parsed = urlsplit(str(address))
        return str(address) if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password else ""
    except (ValueError, UnicodeError):
        return ""


def compact_content(value):
    """Presentation is specific to the returned fact; full values stay in details."""
    platform = service_name(value.get("platform"))
    kind = value.get("type")
    title = str(value.get("title") or value.get("id") or "")
    description = str(value.get("description") or "")
    status = str(value.get("status") or "")
    unsure = not is_confirmed(value)
    if kind == "email_check":
        text = "Сервис сообщил о регистрации" if status == "registration_detected" else "Сведения источника · требуется проверка" if unsure else "Сведения согласно ответу источника"
        return [(platform, "title"), (text, "uncertain" if unsure else "secondary")]
    if kind in BLOCKCHAIN_TYPES:
        details = value.get("details") or {}
        label = TYPE_NAMES.get(kind, str(kind))
        if value.get("date"):
            label += " · " + str(value["date"]).replace("T", " ")[:19]
        if unsure:
            label += " · требует проверки"
        if kind == "transaction":
            direction = {"in": "Входящий перевод", "out": "Исходящий перевод", "incoming": "Входящий перевод", "outgoing": "Исходящий перевод"}.get(details.get("direction"), "Транзакция")
            amount = details.get("amount")
            asset = details.get("asset") or details.get("currency")
            detail = direction + (" · " + str(amount) + (" " + str(asset) if asset else "") if amount is not None else "")
            transaction = details.get("tx_hash") or title or value.get("id") or ""
            return [(label, "uncertain" if unsure else "secondary"), (detail, "title"), (str(transaction), "muted")]
        return [(label, "uncertain" if unsure else "secondary"), (title, "title")]
    address = source_url(value)
    parsed = urlsplit(address)
    short = parsed.netloc + parsed.path + (("?" + parsed.query) if parsed.query else "") if address else ""
    prefix = str(value.get("platform") or "") + " · "
    if kind == "profile" and title.casefold().startswith(prefix.casefold()):
        title = title[len(prefix):]
    lines = [(platform, "title")]
    if title and title.casefold() != platform.casefold():
        lines.append((title, "primary"))
    if short:
        lines.append((short, "link"))
    if unsure:
        lines.append(("Требуется проверка источника", "uncertain"))
    elif kind != "profile" and description and not short:
        lines.append((description, "secondary"))
    return lines[:4]


def result_dict(value):
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, dict):
        return None
    # Do not synthesize an identifier/title from a task state. Those messages
    # belong to SourceExecution and can never increase this model's row count.
    if not value.get("type") or not (value.get("title") or value.get("id")):
        return None
    if value.get("type") in {"status", "execution", "source_status", "task"}:
        return None
    if "state" in value and not value.get("url") and not value.get("details"):
        return None
    if not value.get("platform"):
        return None
    try:
        return Result.from_dict(value).to_dict()
    except (ValueError, TypeError, AttributeError):
        return None


class ResultListModel(QAbstractListModel):
    count_changed = Signal(int)
    RecordRole = int(Qt.ItemDataRole.UserRole) + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = {}
        self._keys = []
        self.confirmed_count = 0
        self._rows = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._keys)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._keys):
            return None
        value = self.record(index.row())
        if role == self.RecordRole:
            return value
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return "\n".join(str(value.get(key, "")) for key in ("platform", "title", "url", "description") if value.get(key))
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(value.get("url") or value.get("title") or "")
        return None

    def record(self, row):
        return self.records[self._keys[row]] if 0 <= row < len(self._keys) else None

    def upsert(self, value):
        value = result_dict(value)
        if value is None:
            return None
        key = result_key(value)
        if key in self.records:
            old = self.records[key]
            value["sources"] = list(dict.fromkeys(old.get("sources", []) + value.get("sources", [])))
            merged = dict(old.get("details", {}))
            merged.update(value.get("details", {}))
            value["details"] = merged
            self.confirmed_count += int(is_confirmed(value)) - int(is_confirmed(old))
            self.records[key] = value
            index = self.index(self._rows[key], 0)
            self.dataChanged.emit(index, index)
            return False
        row = len(self._keys)
        self.beginInsertRows(QModelIndex(), row, row)
        self._keys.append(key)
        self._rows[key] = row
        self.records[key] = value
        self.confirmed_count += int(is_confirmed(value))
        self.endInsertRows()
        self.count_changed.emit(self.rowCount())
        return True

    def clear(self):
        self.beginResetModel()
        self.records.clear()
        self._keys.clear()
        self._rows.clear()
        self.confirmed_count = 0
        self.endResetModel()
        self.count_changed.emit(0)


class ResultDelegate(QStyledItemDelegate):
    """Compact evidence rows with an inline source action, no row widgets."""
    open_requested = Signal(str)
    details_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_values, self._selection_values = {}, {}
        self._transition_callbacks = {}
        self._hover_animation = QVariantAnimation(self)
        self._selection_animation = QVariantAnimation(self)
        for animation in (self._hover_animation, self._selection_animation):
            animation.setDuration(120)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if parent is not None:
            parent.entered.connect(lambda index: self._transition('hover', index.row()))
            parent.viewport().installEventFilter(self)
            parent.selectionModel().currentChanged.connect(lambda current, previous: self._transition('selection', current.row()))
            parent.model().modelReset.connect(self._reset)

    def _reset(self):
        self._hover_animation.stop()
        self._selection_animation.stop()
        self._hover_values.clear()
        self._selection_values.clear()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Leave:
            self._transition('hover', -1)
        return super().eventFilter(watched, event)

    def _transition(self, kind, row):
        animation = getattr(self, '_' + kind + '_animation')
        values = getattr(self, '_' + kind + '_values')
        animation.stop()
        # At most three rows retain transition values, regardless of model size.
        start = dict(sorted(values.items(), key=lambda item: item[1], reverse=True)[:2])
        target = {row: 1.0} if row >= 0 else {}
        if reduced_motion():
            values.clear()
            values.update(target)
            self.parent().viewport().update()
            return
        if kind in self._transition_callbacks:
            animation.valueChanged.disconnect(self._transition_callbacks[kind])
        def advance(progress):
            values.clear()
            for key in start.keys() | target.keys():
                value = start.get(key, 0) + (target.get(key, 0) - start.get(key, 0)) * float(progress)
                if value > .002:
                    values[key] = value
            self.parent().viewport().update()
        animation.valueChanged.connect(advance)
        self._transition_callbacks[kind] = advance
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.start()

    @staticmethod
    def _blend(first, second, fraction):
        first, second = QColor(first), QColor(second)
        return QColor(*(round(a+(b-a)*max(0.0,min(1.0,fraction))) for a,b in zip(first.getRgb()[:3],second.getRgb()[:3])))

    def _metrics(self, option):
        normal = ui_font(14)
        title = ui_font(14, QFont.Weight.DemiBold)
        meta = ui_font(13)
        return normal, title, meta

    def sizeHint(self, option, index):
        value = index.data(ResultListModel.RecordRole) or {}
        lines = compact_content(value)
        return QSize(200, 18 + 20 * len(lines))

    @staticmethod
    def action_rect(bounds):
        return QRect(bounds.right() - 39, bounds.center().y() - 17, 32, 34)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            value = index.data(ResultListModel.RecordRole) or {}
            if self.action_rect(option.rect).contains(event.position().toPoint()):
                address = source_url(value) if value.get('type') != 'email_check' else ''
                if address:
                    self.open_requested.emit(address)
                else:
                    self.details_requested.emit(index)
                return True
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.details_requested.emit(index)
            return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter, option, index):
        value = index.data(ResultListModel.RecordRole) or {}
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = option.rect.adjusted(0, 0, 0, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        hover_value = self._hover_values.get(index.row(), float(hovered) if self._hover_animation.state() != QVariantAnimation.State.Running else 0)
        selection_value = self._selection_values.get(index.row(), float(selected) if self._selection_animation.state() != QVariantAnimation.State.Running else 0)
        background = self._blend('#17212B', '#202F3E', hover_value)
        background = self._blend(background, '#263E54', selection_value)
        painter.fillRect(bounds, background)
        painter.setPen(QColor("#30404E"))
        painter.drawLine(bounds.bottomLeft() + QPointF(12, 0).toPoint(), bounds.bottomRight() - QPointF(12, 0).toPoint())
        content = bounds.adjusted(12, 9, -46, -9)
        normal, title, meta = self._metrics(option)
        colors = {"title": "#F1F3F5", "primary": "#F1F3F5", "secondary": "#A6B2BF", "muted": "#92A2B3", "link": "#82B3E0", "uncertain": "#C8B88B"}
        y = content.y()
        for text, role in compact_content(value):
            font = title if role == "title" else meta if role in ("secondary", "muted", "uncertain") else normal
            painter.setFont(font)
            painter.setPen(QColor(colors[role]))
            mode = Qt.TextElideMode.ElideMiddle if role in ("link", "muted") else Qt.TextElideMode.ElideRight
            shown = QFontMetrics(font).elidedText(str(text), mode, max(1, content.width()))
            painter.drawText(QRect(content.x(), y, content.width(), 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, shown)
            y += 20
        action = self.action_rect(bounds)
        if hover_value or selection_value:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._blend(background, '#344E66', max(hover_value, selection_value)))
            painter.drawRoundedRect(action, 6, 6)
        painter.setFont(normal)
        inline = source_url(value) if value.get('type') != 'email_check' else ''
        painter.setPen(QColor("#82B3E0" if inline else "#A6B2BF"))
        painter.drawText(action, Qt.AlignmentFlag.AlignCenter, "↗" if inline else "›")
        painter.restore()
