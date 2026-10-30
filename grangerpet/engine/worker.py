"""Standalone legacy-tool bridge: stdin JSON, stdout JSONL, no Qt imports."""
from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path
import sys
import tempfile


def probe(source, options):
    """Import actual adapter entry dependencies without a search or login."""
    import importlib
    import importlib.util
    import shutil
    root = Path(options["tools_root"])
    mapping = {"maigret": ("maigret-main", "maigret.checking"), "blackbird": ("blackbird-main/src", "modules.core.username"),
               "holehe": ("holehe-master", "holehe.core"), "snoop": ("snoop-master", "snoop"),
               "telegram": ("", "telethon"), "vk": ("vk_api-master", "vk_api"),
               "instagram": ("instaloader-master", "instaloader"), "wayback": ("waybackpy-master", "waybackpy"),
               "blockchain": ("Gansar-main", "app.aggregator.analyzer")}
    if source == "social_analyzer":
        spec = importlib.util.spec_from_file_location("grangerpet_probe_social", root / "social-analyzer-main/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        relative, module = mapping[source]
        if relative:
            sys.path.insert(0, str(root / relative))
        if source == "snoop":
            shutil.copyfile(root / "snoop-master/domainlist.txt", "domainlist.txt")
        importlib.import_module(module)
    required = {"maigret": [root / "maigret-main/maigret/resources/data.json"],
                "blackbird": [root / "blackbird-main/data/wmn-data.json", root / ".toolenvs/blackbird/wmn-data.json"],
                "snoop": [root / "snoop-master/BDdemo"]}.get(source, [])
    if required and not any(path.is_file() and path.stat().st_size > 10 for path in required):
        return {"source": source, "status": "unavailable", "error_code": "missing_database", "results": [], "message": "Нет необходимой локальной базы источника."}
    return {"source": source, "status": "ready", "results": [], "message": "Реальный импорт адаптера и локальные ресурсы проверены."}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    output = sys.stdout
    def emit(event):
        output.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        output.flush()
    try:
        raw = sys.stdin.readline(16_000_001)
        if len(raw) > 16_000_000:
            raise ValueError("request too large")
        request = json.loads(raw)
        source, query, options = request["source"], request["query"], request.get("options", {})
        if source!='blockchain' and len(raw)>100_000:raise ValueError('request too large')
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        logging.disable(logging.CRITICAL)
        # Legacy modules can create output dirs or start terminal-oriented loggers.
        # Contain those side effects in disposable cwd and discard textual output.
        with tempfile.TemporaryDirectory(prefix="grangerpet-source-") as temporary:
            original_cwd = Path.cwd()
            try:
                os.chdir(temporary)
                with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    if options.get("operation") == "probe":
                        outcome = probe(source, options)
                    elif source in ("telegram", "vk", "instagram", "wayback"):
                        from platforms import run_adapter
                    elif source == "blockchain":
                        from blockchain import run_adapter
                    else:
                        from local_tools import run_adapter
                    # Callback is strictly internal and is never JSON serialized.
                    if options.get("operation") != "probe":
                        options["_emit"] = emit
                        outcome = run_adapter(source, query, options)
            finally:
                os.chdir(original_cwd)
        emit({"event": "final", "outcome": outcome})
        return 0
    except (ImportError, ModuleNotFoundError) as exc:
        missing = getattr(exc, "name", None)
        # Module names only; never stringify vendor exception messages or queries.
        emit({"event": "final", "outcome": {"status": "unavailable", "error_code": "missing_dependency", "missing_module": missing, "results": [],
              "message": "Не установлены зависимости источника" + (f" ({missing})" if missing else "") + ". Запустите настройку подключений."}})
        return 0
    except (Exception, SystemExit):
        emit({"event": "final", "outcome": {"status": "error", "error_code": "probe_failed" if 'options' in locals() and options.get('operation') == 'probe' else "adapter_error", "results": [],
              "message": "Локальный источник не смог выполнить запрос. Проверьте совместимость окружения и подключение."}})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
