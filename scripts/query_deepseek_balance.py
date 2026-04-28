#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/user/balance"
DEFAULT_SILICONFLOW_ENDPOINT = "https://api.siliconflow.cn/v1/user/info"
DEFAULT_DEEPSEEK_KEY_FILE = "/home/ubuntu/.fastgpt_keys/deepseek_api_key"
DEFAULT_SILICONFLOW_KEY_FILE = "/home/ubuntu/.fastgpt_keys/siliconflow_api_key"


def read_api_key(raw_key: str | None, key_file: str | None, env_name: str, provider_label: str) -> str:
    if raw_key and raw_key.strip():
        return raw_key.strip()
    if key_file:
        path = Path(key_file)
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    value = os.getenv(env_name, "").strip()
    if value:
        return value
    raise SystemExit(f"{provider_label} API key is required. Set {env_name} or pass --api-key-file.")


def get_json(api_key: str, endpoint: str, timeout: int, provider_label: str) -> dict[str, Any]:
    request = Request(
        endpoint,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{provider_label} HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"{provider_label} URL error: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{provider_label} returned non-json response: {body[:500]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{provider_label} returned unexpected response: {body[:500]}")
    return data


def get_deepseek_balance(api_key: str, endpoint: str, timeout: int) -> dict[str, Any]:
    return get_json(api_key, endpoint, timeout, "DeepSeek balance")


def get_siliconflow_user_info(api_key: str, endpoint: str, timeout: int) -> dict[str, Any]:
    return get_json(api_key, endpoint, timeout, "SiliconFlow user info")


def print_deepseek_summary(data: dict[str, Any]) -> None:
    print("provider: deepseek")
    print(f"is_available: {data.get('is_available')}")
    infos = data.get("balance_infos")
    if not isinstance(infos, list):
        return
    for index, item in enumerate(infos, start=1):
        if not isinstance(item, dict):
            continue
        currency = item.get("currency") or item.get("currency_type") or "unknown"
        total = item.get("total_balance") or item.get("balance") or "-"
        granted = item.get("granted_balance") or "-"
        topped_up = item.get("topped_up_balance") or "-"
        print(f"[{index}] currency={currency} total={total} granted={granted} topped_up={topped_up}")


def _find_first(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in keys:
            if key in nested:
                return nested.get(key)
    return None


def print_siliconflow_summary(data: dict[str, Any]) -> None:
    print("provider: siliconflow")
    status = _find_first(data, ("status", "code", "message"))
    if status is not None:
        print(f"status: {status}")
    user_id = _find_first(data, ("id", "user_id", "userId", "uid"))
    if user_id is not None:
        print(f"user: {user_id}")
    name = _find_first(data, ("name", "username", "email"))
    if name is not None:
        print(f"name: {name}")
    balance = _find_first(data, ("totalBalance", "total_balance", "chargeBalance", "charge_balance", "balance", "credit", "credits"))
    if balance is not None:
        print(f"balance: {balance}")
    charge_balance = _find_first(data, ("chargeBalance", "charge_balance"))
    if charge_balance is not None and charge_balance != balance:
        print(f"charge_balance: {charge_balance}")


def query_one(provider: str, args: argparse.Namespace) -> dict[str, Any]:
    if provider == "deepseek":
        api_key = read_api_key(
            args.api_key,
            args.api_key_file or DEFAULT_DEEPSEEK_KEY_FILE,
            "DEEPSEEK_API_KEY",
            "DeepSeek",
        )
        return get_deepseek_balance(api_key, args.deepseek_endpoint, args.timeout)
    if provider == "siliconflow":
        api_key = read_api_key(
            args.api_key,
            args.api_key_file or DEFAULT_SILICONFLOW_KEY_FILE,
            "SILICONFLOW_API_KEY",
            "SiliconFlow",
        )
        return get_siliconflow_user_info(api_key, args.siliconflow_endpoint, args.timeout)
    raise RuntimeError(f"Unsupported provider: {provider}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query DeepSeek balance or SiliconFlow user info.")
    parser.add_argument("--provider", choices=("deepseek", "siliconflow", "all"), default="deepseek", help="Provider to query.")
    parser.add_argument("--endpoint", help="Backward-compatible alias for --deepseek-endpoint.")
    parser.add_argument("--deepseek-endpoint", default=DEFAULT_DEEPSEEK_ENDPOINT, help="DeepSeek balance endpoint.")
    parser.add_argument("--siliconflow-endpoint", default=DEFAULT_SILICONFLOW_ENDPOINT, help="SiliconFlow user info endpoint.")
    parser.add_argument("--api-key", help="API key. Prefer provider env vars or --api-key-file to avoid shell history exposure.")
    parser.add_argument("--api-key-file", help="Path to a file containing the provider API key.")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds.")
    parser.add_argument("--summary", action="store_true", help="Print a concise summary instead of raw JSON.")
    args = parser.parse_args()
    if args.endpoint:
        args.deepseek_endpoint = args.endpoint

    providers = ("deepseek", "siliconflow") if args.provider == "all" else (args.provider,)
    raw_results: dict[str, Any] = {}
    for index, provider in enumerate(providers):
        data = query_one(provider, args)
        if args.summary:
            if index:
                print()
            if provider == "deepseek":
                print_deepseek_summary(data)
            else:
                print_siliconflow_summary(data)
        else:
            raw_results[provider] = data

    if not args.summary:
        if len(raw_results) == 1:
            provider, data = next(iter(raw_results.items()))
            print(json.dumps({"provider": provider, "response": data}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(raw_results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
