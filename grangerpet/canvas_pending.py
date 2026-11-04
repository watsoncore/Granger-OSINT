"""Bounded shutdown drain and encrypted, inert recovery of canvas intentions."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import re
import uuid

from .credentials import CredentialsStore
from .portable_vault import atomic_write

MAX_PENDING_BYTES = 32_000_000
MAX_INTENTS = 1024
_ID = re.compile(r"[a-f0-9]{32}")
_OPS = {"edit", "new", "open", "list", "undo", "redo", "duplicate", "delete", "insert",
        "tool", "analyze", "from_search", "attach", "import", "export", "media"}
_FIELDS = {
    "edit": {"operation", "arguments"}, "new": {"title", "description"}, "open": {"id"},
    "list": set(), "undo": set(), "redo": set(), "duplicate": set(), "delete": {"confirmed"},
    "insert": {"token", "evidence_ids"}, "tool": {"entity_id", "tool", "query", "arguments", "limit"},
    "analyze": {"ids", "intent"}, "from_search": {"investigation_id"}, "attach": {"attachment_id"},
    "import": set(), "export": set(), "media": {"entity_id"},
}
_FORBIDDEN = {"path", "filename", "local_path", "source_root", "runtime_python", "command", "shell",
              "api_key", "apikey", "password", "authorization", "cookie", "cookies", "secret", "secrets"}


def _finite(value, depth=0, *, insert_token=False):
    if depth > 12:
        raise ValueError("Pending canvas data is too deep")
    if value is None or isinstance(value, (str, bool)):
        return value
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite canvas value")
        return value
    if isinstance(value, list):
        if len(value) > 20_000:
            raise ValueError("Canvas list is too large")
        return [_finite(v, depth + 1) for v in value]
    if isinstance(value, dict):
        def private(key):
            if not isinstance(key,str):return True
            normalized=key.casefold()
            return (normalized in _FORBIDDEN or normalized.endswith(('_api_key','_password','_secret','_token'))
                    or normalized=='token' and not (insert_token and depth==0))
        if len(value) > 20_000 or any(private(k) for k in value):
            raise ValueError("Private or executable pending field")
        return {k: _finite(v, depth + 1) for k, v in value.items()}
    raise ValueError("Invalid canvas value")


def validate_snapshot(value):
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_PENDING_BYTES:
            raise ValueError("Pending canvas data exceeds 32 MB")
        value = json.loads(value)
    if not isinstance(value, dict) or set(value) - {"intents", "current", "error"}:
        raise ValueError("Invalid pending canvas snapshot")
    intents = value.get("intents")
    if not isinstance(intents, list) or len(intents) > MAX_INTENTS:
        raise ValueError("Pending canvas queue exceeds 1024 intentions")
    normalized, tokens = [], set()
    for item in intents:
        if not isinstance(item, dict) or set(item) - {"op", "payload", "target", "token"}:
            raise ValueError("Invalid pending intention")
        op, payload, target, token = (item.get(k) for k in ("op", "payload", "target", "token"))
        if op not in _OPS or not isinstance(payload, dict) or not isinstance(token, str) or not _ID.fullmatch(token) or token in tokens:
            raise ValueError("Invalid pending operation or mutation identifier")
        if target is not None and (not isinstance(target, str) or not _ID.fullmatch(target)):
            raise ValueError("Invalid pending canvas target")
        if set(payload) - _FIELDS[op]:
            raise ValueError("Unknown pending operation field")
        normalized.append({"op": op, "payload": _finite(payload,insert_token=op=='insert'), "token": token, **({"target": target} if target else {})})
        tokens.add(token)
    current = value.get("current")
    if current is not None:
        if (not isinstance(current, dict) or set(current) != {"id", "revision"} or
                not isinstance(current["id"], str) or not _ID.fullmatch(current["id"]) or
                type(current["revision"]) is not int or current["revision"] < 0):
            raise ValueError("Invalid pending current canvas")
    error = value.get("error", "")
    if not isinstance(error, str) or len(error) > 1000:
        raise ValueError("Invalid pending error")
    result = {"intents": normalized, "error": error, **({"current": deepcopy(current)} if current else {})}
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_PENDING_BYTES:
        raise ValueError("Pending canvas data exceeds 32 MB")
    return result


class PendingCanvasStore:
    def __init__(self, canvas_store):
        self.canvas_store = canvas_store

    def _path(self, identifier):
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            raise ValueError("Invalid pending draft identifier")
        return self.canvas_store.directory / ("pending-" + identifier + ".dpapi")

    def save(self, snapshot):
        snapshot = validate_snapshot(snapshot)
        if not snapshot["intents"]:
            return None
        identifier = uuid.uuid4().hex
        data = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
        atomic_write(self._path(identifier), CredentialsStore._protect(data))
        return identifier

    def clear(self, identifier):
        path = self._path(identifier)
        if path.is_symlink():
            raise ValueError("Unsafe pending draft")
        path.unlink(missing_ok=True)

    def recovery(self):
        root = self.canvas_store.directory
        paths = sorted(root.glob("pending-*.dpapi"), key=lambda p: p.stat().st_mtime_ns, reverse=True) if root.exists() else []
        for path in paths:
            identifier = path.stem.removeprefix("pending-")
            if not _ID.fullmatch(identifier) or path.is_symlink() or path.stat().st_size > MAX_PENDING_BYTES + 65536:
                continue
            try:
                snapshot = validate_snapshot(CredentialsStore._protect(path.read_bytes(), decrypt=True).decode("utf-8"))
            except (ValueError, OSError, UnicodeError):
                continue  # Keep damaged ciphertext for inspection; never rewrite it.
            receipts = set()
            # New/open intentions can be unbound. Recent immutable documents
            # locate successful late commits even after the bridge was closed.
            targets = {x.get("target") for x in snapshot["intents"] if x.get("target")}
            if snapshot.get("current"):
                targets.add(snapshot["current"]["id"])
            targets.update(item["id"] for item in self.canvas_store.list())
            for target in targets:
                try:
                    doc = self.canvas_store.load(target)
                    receipts.update(v for v in doc.get("mutation_receipts", []) if isinstance(v, str))
                except (ValueError, OSError):
                    continue
            snapshot["intents"] = [item for item in snapshot["intents"] if item["token"] not in receipts]
            if snapshot["intents"]:
                return {"draft_id": identifier, **snapshot}
        return None


def flush_canvas_pending(surface, *, timeout_ms=2500):
    """Keep the channel alive while draining, then retain any unfinished delta.

    prepareShutdown freezes new renderer intake but drains existing intentions.
    This helper never submits a tool/AI call itself or invokes a restored draft.
    """
    from PySide6.QtCore import QEventLoop, QTimer
    bridge = surface.bridge
    controller = bridge._research_canvas
    loop, poll, bound = QEventLoop(), QTimer(), QTimer()
    poll.setInterval(40); bound.setSingleShot(True)
    state = {"snapshot": None, "waiting": False, "finished": False}

    def received(raw):
        state["waiting"] = False
        try:
            snapshot = validate_snapshot(raw)
        except (ValueError, TypeError):
            return
        state["snapshot"] = snapshot
        job = controller.job if controller else None
        if not snapshot["intents"] and job is None:
            state["finished"] = True
            loop.quit()

    def request(prepare=False):
        if state["waiting"]:
            return
        state["waiting"] = True
        method = "prepareShutdown" if prepare else "snapshot"
        script = "JSON.stringify(window.grangerCanvasQueue?." + method + "?.()??{intents:[],error:''})"
        surface.trusted_page.runJavaScript(script, received)

    poll.timeout.connect(request)
    bound.timeout.connect(loop.quit)
    request(True)
    if not state["finished"]:
        poll.start(); bound.start(max(1, min(2500, int(timeout_ms))))
        loop.exec()
    poll.stop(); bound.stop()
    snapshot = state["snapshot"] or {"intents": [], "error": "Renderer did not acknowledge shutdown."}
    active = getattr(controller, "_active_receipt", None) if controller else None
    if active and active.get("intent") and not any(row["token"] == active["intent"]["token"] for row in snapshot["intents"]):
        snapshot["intents"].insert(0, deepcopy(active["intent"]))
    if snapshot["intents"]:
        snapshot["error"] = snapshot.get("error") or "Приложение закрыто до завершения очереди. Повторите сохранённые действия явно."
        if controller is None:
            from .research_canvas_bridge import ResearchCanvasBridge
            controller = ResearchCanvasBridge(bridge)
            bridge._research_canvas = controller
        return {"drained": False, "draft_id": PendingCanvasStore(controller.store).save(snapshot), "pending": len(snapshot["intents"])}
    return {"drained": state["finished"], "pending": 0}
