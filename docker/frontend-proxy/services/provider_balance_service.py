from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEEPSEEK_BALANCE_ENDPOINT = os.getenv("DEEPSEEK_BALANCE_ENDPOINT", "https://api.deepseek.com/user/balance")
SILICONFLOW_USER_ENDPOINT = os.getenv("SILICONFLOW_USER_ENDPOINT", "https://api.siliconflow.cn/v1/user/info")
DEEPSEEK_KEY_FILES = [
    Path(os.getenv("DEEPSEEK_API_KEY_FILE", "/run/fastgpt_keys/deepseek_api_key")),
    Path("/home/ubuntu/.fastgpt_keys/deepseek_api_key"),
]
SILICONFLOW_KEY_FILES = [
    Path(os.getenv("SILICONFLOW_API_KEY_FILE", "/run/fastgpt_keys/siliconflow_api_key")),
    Path("/home/ubuntu/.fastgpt_keys/siliconflow_api_key"),
]
BALANCE_CACHE_TTL = int(os.getenv("PROVIDER_BALANCE_CACHE_TTL", "60"))

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"updatedAt": 0, "providers": []}


def _read_key(paths: list[Path], env_name: str) -> str:
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    for path in paths:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    return ""


def _get_json(endpoint: str, api_key: str, timeout: int = 20) -> dict[str, Any]:
    request = Request(
        endpoint,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _first_number(data: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    candidates: list[Any] = []
    for key in keys:
        candidates.append(data.get(key))
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in keys:
            candidates.append(nested.get(key))
    for value in candidates:
        try:
            if value is None or value == "":
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _format_amount(value: float | None, currency: str = "") -> str:
    if value is None:
        return "--"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{currency}{text}" if currency else text


def _error_payload(provider_id: str, name: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, HTTPError):
        detail = exc.read().decode("utf-8", errors="replace")[:240]
        message = f"HTTP {exc.code}: {detail}"
    elif isinstance(exc, URLError):
        message = f"URL error: {exc.reason}"
    else:
        message = str(exc)
    return {"id": provider_id, "name": name, "ok": False, "balanceText": "--", "message": message}


def _query_deepseek() -> dict[str, Any]:
    api_key = _read_key(DEEPSEEK_KEY_FILES, "DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DeepSeek API key not configured")
    data = _get_json(DEEPSEEK_BALANCE_ENDPOINT, api_key)
    infos = data.get("balance_infos")
    amount = None
    currency = ""
    if isinstance(infos, list) and infos:
        first = infos[0] if isinstance(infos[0], dict) else {}
        amount = _first_number(first, ("total_balance", "totalBalance", "topped_up_balance", "granted_balance"))
        currency = str(first.get("currency") or "")
    return {
        "id": "deepseek",
        "name": "DeepSeek",
        "ok": True,
        "available": bool(data.get("is_available")),
        "balance": amount,
        "currency": currency,
        "balanceText": _format_amount(amount, "¥" if currency.upper() == "CNY" else currency),
    }


def _query_siliconflow() -> dict[str, Any]:
    api_key = _read_key(SILICONFLOW_KEY_FILES, "SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("SiliconFlow API key not configured")
    data = _get_json(SILICONFLOW_USER_ENDPOINT, api_key)
    amount = _first_number(data, ("totalBalance", "total_balance", "chargeBalance", "charge_balance", "balance"))
    return {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "ok": True,
        "available": bool(data.get("status", True)),
        "balance": amount,
        "currency": "CNY",
        "balanceText": _format_amount(amount, "¥"),
    }


def _query_provider(query: Any, provider_id: str, name: str) -> dict[str, Any]:
    try:
        return query()
    except Exception as exc:
        return _error_payload(provider_id, name, exc)


def query_provider_balances(*, force: bool = False) -> dict[str, Any]:
    now = int(time.time())
    with _CACHE_LOCK:
        if not force and _CACHE.get("providers") and now - int(_CACHE.get("updatedAt") or 0) < BALANCE_CACHE_TTL:
            return {**_CACHE, "cached": True, "cacheTtl": BALANCE_CACHE_TTL}

    providers = [
        _query_provider(_query_deepseek, "deepseek", "DeepSeek"),
        _query_provider(_query_siliconflow, "siliconflow", "SiliconFlow"),
    ]
    payload = {"updatedAt": now, "providers": providers, "cached": False, "cacheTtl": BALANCE_CACHE_TTL}
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE.update({"updatedAt": now, "providers": providers})
    return payload
