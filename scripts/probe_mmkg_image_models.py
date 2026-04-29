#!/usr/bin/env python3
"""Probe whether an OpenCode provider exposes image generation models."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.json"
TARGET_MODEL = "gpt-image-2"


def load_provider_config(config_path: Path, provider_name: str) -> tuple[str, str]:
    env_prefix = provider_name.upper().replace("-", "_")
    base_url = os.getenv(f"{env_prefix}_BASE_URL", "").strip()
    api_key = os.getenv(f"{env_prefix}_API_KEY", "").strip()
    if base_url and api_key:
        return base_url.rstrip("/"), api_key

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"OpenCode config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"OpenCode config is not valid JSON: {config_path}: {exc}") from exc

    provider = config.get("provider", {}).get(provider_name, {})
    options = provider.get("options", {})
    base_url = base_url or str(options.get("baseURL", "")).strip()
    api_key = api_key or str(options.get("apiKey", "")).strip()
    if not base_url or not api_key:
        raise SystemExit(
            f"{provider_name} provider config is incomplete. "
            f"Set {env_prefix}_BASE_URL and {env_prefix}_API_KEY or update OpenCode config."
        )
    return base_url.rstrip("/"), api_key


def request_json(url: str, api_key: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "curl/8.5.0",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: dict[str, Any] | str = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed
    except URLError as exc:
        return 0, f"URL error: {exc}"


def extract_model_ids(models_response: dict[str, Any] | str) -> list[str]:
    if not isinstance(models_response, dict):
        return []
    data = models_response.get("data")
    if not isinstance(data, list):
        return []
    ids = []
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return sorted(ids)


def summarize_error(body: dict[str, Any] | str) -> str:
    if isinstance(body, str):
        return body[:500]
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("code") or error
        return str(message)[:500]
    return json.dumps(body, ensure_ascii=False)[:500]


def probe_image_endpoint(base_url: str, api_key: str, model: str, prompt: str, size: str) -> tuple[int, dict[str, Any] | str]:
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "b64_json",
    }
    return request_json(f"{base_url}/images/generations", api_key, method="POST", payload=payload)


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return args.prompt_file.read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    return "A minimal blue square icon on a white background."


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe an OpenCode provider for gpt-image-2 support.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="OpenCode config path")
    parser.add_argument("--provider", default="mmkg", help="Provider name in OpenCode config, for example mmkg or xcode")
    parser.add_argument("--model", default=TARGET_MODEL, help="Image model id to test")
    parser.add_argument("--prompt", help="Prompt to use for image generation")
    parser.add_argument("--prompt-file", type=Path, help="Read image generation prompt from a text file")
    parser.add_argument("--size", default="1024x1024", help="Image size passed to the provider")
    parser.add_argument("--skip-generate", action="store_true", help="Only list models; do not call image generation")
    parser.add_argument("--save-image", type=Path, help="Save generated image if the probe succeeds")
    args = parser.parse_args()

    base_url, api_key = load_provider_config(args.config, args.provider)
    print(f"provider: {args.provider}")
    print(f"base_url: {base_url}")

    models_status, models_body = request_json(f"{base_url}/models", api_key)
    model_ids = extract_model_ids(models_body)
    print(f"models_status: {models_status}")
    print(f"models_count: {len(model_ids)}")
    if model_ids:
        image_like = [model_id for model_id in model_ids if "image" in model_id.lower() or "dall" in model_id.lower()]
        print("configured_image_like_models:", ", ".join(image_like) if image_like else "none")
        print(f"has_{args.model}: {str(args.model in model_ids).lower()}")
    else:
        print("models_error:", summarize_error(models_body))

    if args.skip_generate:
        return 0

    prompt = load_prompt(args)
    image_status, image_body = probe_image_endpoint(base_url, api_key, args.model, prompt, args.size)
    print(f"image_generation_status: {image_status}")
    if image_status == 200 and isinstance(image_body, dict):
        data = image_body.get("data")
        first = data[0] if isinstance(data, list) and data else {}
        if isinstance(first, dict) and first.get("b64_json"):
            print(f"image_generation_supported: true")
            if args.save_image:
                args.save_image.parent.mkdir(parents=True, exist_ok=True)
                args.save_image.write_bytes(base64.b64decode(first["b64_json"]))
                print(f"saved_image: {args.save_image}")
        else:
            print("image_generation_supported: true")
            print("image_generation_response:", json.dumps(image_body, ensure_ascii=False)[:500])
        return 0

    print("image_generation_supported: false")
    print("image_generation_error:", summarize_error(image_body))
    return 1


if __name__ == "__main__":
    sys.exit(main())
