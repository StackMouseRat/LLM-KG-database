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


DEFAULT_ENDPOINT = "https://api.deepseek.com/user/balance"


def read_api_key(raw_key: str | None, key_file: str | None) -> str:
    if raw_key and raw_key.strip():
        return raw_key.strip()
    if key_file:
        value = Path(key_file).read_text(encoding="utf-8").strip()
        if value:
            return value
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if value:
        return value
    raise SystemExit("DeepSeek API key is required. Set DEEPSEEK_API_KEY or pass --api-key-file.")


def get_balance(api_key: str, endpoint: str, timeout: int) -> dict[str, Any]:
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
        raise RuntimeError(f"DeepSeek balance HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek balance URL error: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DeepSeek balance returned non-json response: {body[:500]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"DeepSeek balance returned unexpected response: {body[:500]}")
    return data


def print_summary(data: dict[str, Any]) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Query DeepSeek account balance.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="DeepSeek balance endpoint.")
    parser.add_argument("--api-key", help="DeepSeek API key. Prefer DEEPSEEK_API_KEY or --api-key-file to avoid shell history exposure.")
    parser.add_argument("--api-key-file", help="Path to a file containing the DeepSeek API key.")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds.")
    parser.add_argument("--summary", action="store_true", help="Print a concise summary instead of raw JSON.")
    args = parser.parse_args()

    api_key = read_api_key(args.api_key, args.api_key_file)
    data = get_balance(api_key, args.endpoint, args.timeout)
    if args.summary:
        print_summary(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
