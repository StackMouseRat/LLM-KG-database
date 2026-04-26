from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "http://127.0.0.1:3000/api/v1/chat/completions"


def read_api_key(raw_key: str | None, key_file: str | None) -> str:
    if raw_key:
        return raw_key.strip()
    if key_file:
        value = Path(key_file).read_text(encoding="utf-8").strip()
        if value:
            return value
    raise SystemExit("API key is required. Use --api-key or --api-key-file.")


def build_payload(prompt: str, template: str, stream: bool, detail: bool) -> dict[str, Any]:
    variables: dict[str, Any] = {"提示词": prompt}
    if template:
        variables["模板"] = template
    return {
        "stream": stream,
        "detail": detail,
        "variables": variables,
    }


def post_json(endpoint: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc}") from exc
    return json.loads(body)


def post_stream(endpoint: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
        },
    )

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    flow_responses: list[Any] = []
    event_name = ""
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal event_name, data_lines, flow_responses
        if not event_name and not data_lines:
            return

        payload_text = "\n".join(data_lines).strip()
        if not payload_text:
            event_name = ""
            data_lines = []
            return

        try:
            event_payload = json.loads(payload_text)
        except json.JSONDecodeError:
            event_payload = payload_text

        if event_name == "answer" and isinstance(event_payload, dict):
            choices = event_payload.get("choices")
            if isinstance(choices, list) and choices:
                delta = choices[0].get("delta", {})
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        content_parts.append(content)
                    reasoning = delta.get("reasoning_content")
                    if isinstance(reasoning, str) and reasoning:
                        reasoning_parts.append(reasoning)
        elif event_name == "flowResponses" and isinstance(event_payload, list):
            flow_responses = event_payload

        event_name = ""
        data_lines = []

    try:
        with urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if not line.strip():
                    flush_event()
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            flush_event()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc}") from exc

    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "".join(content_parts),
                }
            }
        ],
        "reasoningText": "".join(reasoning_parts),
        "responseData": flow_responses,
    }


def extract_text(response: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    answer_text = ""
    reasoning_text = ""
    plugin_output: dict[str, Any] = {}

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                answer_text = content.strip()

    response_data = response.get("responseData", [])
    if isinstance(response_data, list):
        for node in response_data:
            if not isinstance(node, dict):
                continue
            if node.get("moduleType") == "chatNode" and not reasoning_text:
                value = node.get("reasoningText")
                if isinstance(value, str):
                    reasoning_text = value.strip()
            if node.get("moduleType") == "pluginOutput":
                candidate = node.get("pluginOutput")
                if isinstance(candidate, dict):
                    plugin_output = candidate

    if not reasoning_text:
        value = response.get("reasoningText")
        if isinstance(value, str):
            reasoning_text = value.strip()

    if not answer_text and isinstance(plugin_output.get("回复"), str):
        answer_text = str(plugin_output.get("回复")).strip()

    return answer_text, reasoning_text, plugin_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a FastGPT plugin with 模板/提示词 inputs.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="FastGPT chat completions endpoint.")
    parser.add_argument("--api-key", help="FastGPT plugin key.")
    parser.add_argument("--api-key-file", help="Path to a file containing the FastGPT plugin key.")
    parser.add_argument("--prompt", required=True, help="Value for plugin variable `提示词`.")
    parser.add_argument("--template", default="", help="Optional value for plugin variable `模板`.")
    parser.add_argument("--stream", action="store_true", help="Use SSE streaming mode.")
    parser.add_argument("--no-detail", action="store_true", help="Disable detail=true.")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout in seconds.")
    parser.add_argument("--show-raw", action="store_true", help="Print raw JSON response.")
    args = parser.parse_args()

    api_key = read_api_key(args.api_key, args.api_key_file)
    payload = build_payload(
        prompt=args.prompt,
        template=args.template,
        stream=args.stream,
        detail=not args.no_detail,
    )

    response = (
        post_stream(args.endpoint, api_key, payload, args.timeout)
        if args.stream
        else post_json(args.endpoint, api_key, payload, args.timeout)
    )

    answer_text, reasoning_text, plugin_output = extract_text(response)

    print("== Request ==")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("\n== Parsed Output ==")
    print(f"answer_text: {answer_text}")
    print(f"reasoning_text: {reasoning_text}")
    print(f"plugin_output: {json.dumps(plugin_output, ensure_ascii=False)}")

    if args.show_raw:
        print("\n== Raw Response ==")
        print(json.dumps(response, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
