"""Use the existing Gansar analyzer as a bounded headless internal engine.

No Gansar CLI, HTML exporter, browser, graphs, database export or alternate UI
is launched. Production attribution resources remain in the original checkout.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys
from urllib.parse import quote

EXPLORERS = {
    "btc": "https://mempool.space/address/", "doge": "https://dogechain.info/address/",
    "eth": "https://etherscan.io/address/", "bsc": "https://bscscan.com/address/",
    "polygon": "https://polygonscan.com/address/", "arbitrum": "https://arbiscan.io/address/",
    "optimism": "https://optimistic.etherscan.io/address/", "avalanche": "https://snowtrace.io/address/",
    "tron": "https://tronscan.org/#/address/", "ton": "https://tonviewer.com/", "solana": "https://solscan.io/account/",
}


def _serial(value):
    if hasattr(value, "model_dump"):
        return _serial(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items() if key != "raw"}
    if isinstance(value, (list, tuple)):
        return [_serial(item) for item in value]
    if isinstance(value, (Decimal, datetime, date)):
        return str(value) if isinstance(value, Decimal) else value.isoformat()
    return value


def _url(chain, address):
    return EXPLORERS.get(chain, "") + quote(str(address), safe="-_:.") if chain in EXPLORERS else ""


def _result(identifier, title, kind, chain, url, description, details, date=None, status="verified", sources=None):
    return {"id": str(identifier), "title": str(title), "type": kind,
            "platform": "Блокчейн · " + str(chain).upper(), "url": str(url or ""),
            "description": str(description or "")[:4000], "date": date,
            "details": _serial(details), "status": status,
            "sources": list(dict.fromkeys(["blockchain", "Gansar"] + (sources or [])))}


def normalize_report(report: dict, limit=20) -> list[dict]:
    """Normalize observations while retaining source/confidence/coverage fields."""
    limit = max(1, min(int(limit), 50))
    results = []
    target = report.get("target_address", "")
    for balance in report.get("balances", []):
        chain, asset = balance.get("chain", ""), balance.get("asset", "")
        amount = balance.get("amount_decimal")
        if amount is None:
            amount = balance.get("amount")
        if amount is None:
            continue
        results.append(_result(f"balance:{chain}:{balance.get('address', target)}:{asset}",
            f"{asset} · {amount}", "balance", chain, balance.get("url") or _url(chain, target),
            f"Публично наблюдаемый баланс адреса {target}. Источник: {balance.get('source', '')}.", balance,
            sources=[balance.get("source", "")]))
    for transaction in report.get("transactions", [])[:limit]:
        chain, tx_hash = transaction.get("chain", ""), transaction.get("tx_hash", "")
        if not tx_hash:
            continue
        amount = transaction.get("amount_decimal")
        if amount is None:
            amount = transaction.get("amount")
        direction = {"in": "Входящая", "out": "Исходящая", "self": "Собственная"}.get(transaction.get("direction"), "Транзакция")
        description = f"{direction}: {amount if amount is not None else 'сумма не предоставлена'} {transaction.get('asset') or ''}. "
        description += f"От: {transaction.get('from_address') or 'не предоставлено'}; к: {transaction.get('to_address') or 'не предоставлено'}."
        results.append(_result(f"transaction:{chain}:{transaction.get('event_id') or tx_hash}", tx_hash,
            "transaction", chain, transaction.get("url") or _url(chain, target), description, transaction,
            transaction.get("timestamp"), sources=[transaction.get("source", "")]))
    for token in report.get("tokens", [])[:limit]:
        chain = token.get("chain", "")
        symbol = token.get("symbol") or token.get("name") or token.get("contract") or "Актив"
        holding = token.get("holding_status", "unknown")
        amount = token.get("amount_decimal")
        if amount is None:
            amount = token.get("amount")
        results.append(_result(f"token:{chain}:{target}:{token.get('contract') or symbol}", symbol, "asset", chain,
            token.get("url") or _url(chain, token.get("contract") or target),
            f"Статус владения: {holding}; количество: {amount if amount is not None else 'не предоставлено'}.",
            token, status="verified" if holding == "current" else "check", sources=[token.get("source", "")]))
    for asset in report.get("ton_assets", [])[:limit]:
        verified = bool(asset.get("ownership_verified"))
        results.append(_result(f"ton_asset:{asset.get('asset_id')}", asset.get("title") or asset.get("name") or asset.get("asset_id"),
            "asset", "ton", asset.get("evidence_url") or asset.get("external_url") or _url("ton", asset.get("asset_id", target)),
            f"{asset.get('type')}; владение: {asset.get('ownership_status', 'unknown')}; проверка on-chain: {verified}.",
            asset, asset.get("ownership_observed_at"), "verified" if verified else "check", [asset.get("source", "")]))
    for label in report.get("labels", [])[:limit]:
        chain = label.get("chain", "")
        results.append(_result(f"label:{chain}:{label.get('address')}:{label.get('label')}:{label.get('source')}",
            label.get("label", "Метка источника"), "label", chain, _url(chain, label.get("address", target)),
            f"Метка источника; уверенность: {label.get('confidence', 'не предоставлена')}. Не устанавливает личность владельца.",
            label, status="check", sources=[label.get("source", "")]))
    for counterpart in report.get("counterparties", [])[:min(limit, 10)]:
        if not counterpart.get("tx_count"):
            continue
        chain, address = counterpart.get("chain", ""), counterpart.get("address", "")
        results.append(_result(f"counterparty:{chain}:{target}:{address}", address, "relationship", chain, _url(chain, address),
            f"Наблюдаемые транзакционные взаимодействия: {counterpart['tx_count']}. Совпадение владельцев из этого не следует.",
            counterpart, counterpart.get("last_seen"), "check"))
    if results:
        results[0]["details"]["target_address"] = target
        results[0]["details"]["detected_chains"] = list(report.get("detected_chains", []))
        results[0]["details"]["coverage"] = _serial(report.get("coverage", {}))
        results[0]["details"]["source_health"] = _serial(report.get("source_health", []))
        results[0]["details"]["warnings"] = list(report.get("warnings", []))[:20]
    # Keep useful categories visible even when a busy wallet has many transfers.
    groups = {}
    for item in results:
        groups.setdefault(item["type"], []).append(item)
    balanced = []
    while groups and len(balanced) < limit:
        for kind in list(groups):
            balanced.append(groups[kind].pop(0))
            if not groups[kind]:
                del groups[kind]
            if len(balanced) >= limit:
                break
    return balanced


async def _analyze(query, options):
    from app.aggregator.analyzer import analyze_address
    from app.utils.detect import detect_candidates
    from app.utils.http import close_shared_clients
    text = query["text"].strip()
    for prefix in ("blockchain:", "crypto:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
    timeout = max(5.0, min(float(query.get("timeout", 25)), 40.0))
    limit = max(1, min(int(query.get("limit", 20)), 50))
    selected = query.get("options", {}).get("chain") or options.get("chain")
    selected_chains = [selected] if selected in EXPLORERS else None
    publish = options.get("_emit")
    published = set()
    def progress(event):
        if callable(publish) and isinstance(event, dict):
            # These are actual stages emitted by analyze_address, never a timer.
            # Keep only stage/count/status fields; no raw provider payload/key.
            publish({"event": "stage", **{key: event[key] for key in ("stage", "source", "status", "transactions", "assets") if key in event}})
    def checkpoint(partial):
        if not callable(publish):
            return
        for item in normalize_report(_serial(partial), limit):
            if item["id"] not in published:
                published.add(item["id"])
                publish({"event": "result", "result": item})
    seed = None
    try:
        if text.lower().endswith(".eth"):
            from app.sources.ethereum_ens import EthereumEnsSource
            seed = await asyncio.wait_for(EthereumEnsSource(5).resolve_name(text), min(8, timeout / 2))
            profile = seed.ens_profile or {}
            resolved = seed.ens_resolved_address or profile.get("resolved_address")
            if not resolved or not profile.get("forward_verified"):
                return {"source": "blockchain", "status": "empty", "results": [],
                        "message": "ENS-имя не разрешилось с подтверждённой прямой привязкой; адрес не подставлялся."}
            text, selected_chains = resolved, ["eth"]
        detected = detect_candidates(text)
        if not detected:
            return {"source": "blockchain", "status": "error", "results": [],
                    "message": "Gansar не распознал поддерживаемый адрес. Для EVM при необходимости выберите сеть вручную."}
        evm = {"eth", "bsc", "polygon", "arbitrum", "optimism", "avalanche"}
        chosen_chain = selected_chains[0] if selected_chains else None
        if chosen_chain and chosen_chain not in detected and not (chosen_chain in evm and "eth" in detected):
            return {"source": "blockchain", "status": "error", "results": [],
                    "message": "Формат адреса не соответствует выбранной сети. Уточните сеть или включите автоматический выбор."}
        loop = asyncio.get_running_loop()
        report, _ = await asyncio.wait_for(analyze_address(text, timeout_seconds=5.0, max_txs=limit,
                    selected_chains=selected_chains, include_experimental=False,
                    deadline=loop.time() + max(3, timeout - 3), defer_graph=True, ens_seed=seed,
                    on_checkpoint=checkpoint, checkpoint_interval=2.0, progress=progress), timeout)
        data = _serial(report)
        results = normalize_report(data, limit)
        health = data.get("source_health", [])
        usable = any(row.get("status") in ("ok", "partial", "empty") for row in health)
        incomplete = any(row.get("status") not in ("ok", "empty") for row in health)
        state = "partial" if results and incomplete else "complete" if results else "empty" if usable else "unavailable"
        message = ("Получены публичные on-chain наблюдения; полнота и статусы провайдеров сохранены в деталях."
                   if results else "Подключённые блокчейн-источники не вернули наблюдений." if usable
                   else "Блокчейн-провайдеры недоступны, ограничили доступ или требуют настройки API. Результаты не вымышлялись.")
        return {"source": "blockchain", "status": state, "results": results, "message": message,
                "source_health": health, "warnings": data.get("warnings", [])[:20]}
    finally:
        await close_shared_clients()


def run_adapter(source: str, query: dict, options: dict) -> dict:
    root = Path(options.get("tools_root") or options.get("source_root") or Path(__file__).resolve().parents[2]).resolve()
    vendor = root / "Gansar-main"
    if not (vendor / "app" / "aggregator" / "analyzer.py").is_file():
        return {"source": source, "status": "unavailable", "results": [], "message": "Не найден локальный исходный движок Gansar-main."}
    sys.path.insert(0, str(vendor))
    try:
        if isinstance(query.get('options',{}).get('blockchain'),dict):
            if __package__:
                from .blockchain_runner import execute_gansar
            else:
                from blockchain_runner import execute_gansar
            return asyncio.run(execute_gansar(query,options))
        import httpx
        from unittest.mock import patch
        budget = max(5, min(int(options.get("request_limit", query.get("limit", 20))), 50))
        count = {"used": 0, "limited": False}
        original_send = httpx.AsyncClient.send
        async def limited_send(client, request, **kwargs):
            if count["used"] >= budget:
                count["limited"] = True
                raise httpx.RequestError("GrangerPet source request budget exhausted", request=request)
            count["used"] += 1
            return await original_send(client, request, **kwargs)
        with patch.object(httpx.AsyncClient, "send", limited_send):
            outcome = asyncio.run(_analyze(query, options))
        outcome["requests_used"] = count["used"]
        if count["limited"]:
            outcome["message"] += " Достигнут лимит HTTP-запросов; история может быть неполной."
            if outcome.get("results"):
                outcome["status"] = "partial"
        if outcome.get("results"):
            outcome["results"][0]["details"]["request_budget"] = {"limit": budget, "used": count["used"], "exhausted": count["limited"]}
        return outcome
    except ImportError as error:
        return {"source": source, "status": "unavailable", "results": [],
                "message": f"Не подготовлены зависимости внутреннего блокчейн-движка ({type(error).__name__}). Запустите setup_sources.py --groups blockchain."}
    except (TimeoutError, asyncio.TimeoutError):
        return {"source": source, "status": "timeout", "results": [], "message": "Блокчейн-источники превысили общий бюджет времени; скрытый фоновый поиск не продолжался."}
    except Exception as error:
        return {"source": source, "status": "error", "results": [],
                "message": f"Блокчейн-движок завершил запрос с ошибкой ({type(error).__name__}); вымышленных наблюдений нет."}
