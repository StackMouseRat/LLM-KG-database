from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.sse import send_sse


FORMAT_REVIEW_PLUGIN_URL = os.getenv(
    "FORMAT_REVIEW_PLUGIN_URL",
    "http://host.docker.internal:3000/api/v1/chat/completions",
)
FORMAT_REVIEW_PLUGIN_KEY_FILE = os.getenv(
    "FORMAT_REVIEW_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/format_review_plugin_api_key",
)
STRUCTURED_EVALUATION_PLUGIN_URL = os.getenv(
    "STRUCTURED_EVALUATION_PLUGIN_URL",
    FORMAT_REVIEW_PLUGIN_URL,
)
STRUCTURED_EVALUATION_PLUGIN_KEY_FILE = os.getenv(
    "STRUCTURED_EVALUATION_PLUGIN_KEY_FILE",
    "/run/fastgpt_keys/structured_evaluation_plugin_api_key",
)


def read_key(path_text: str) -> str:
    path = Path(path_text)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"plugin key file is empty: {path}")
    return key


def read_format_review_key() -> str:
    return read_key(FORMAT_REVIEW_PLUGIN_KEY_FILE)


def read_structured_evaluation_key() -> str:
    return read_key(STRUCTURED_EVALUATION_PLUGIN_KEY_FILE)


def extract_plugin_text(response: dict[str, Any]) -> tuple[str, str]:
    reasoning = ""
    output = ""
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    output = content
                elif isinstance(content, list):
                    for item in content:
                        if not isinstance(item, dict):
                            continue
                        if item.get("type") == "reasoning":
                            reasoning += str(item.get("reasoning", {}).get("content") or "")
                        if item.get("type") == "text":
                            output += str(item.get("text", {}).get("content") or "")
    for node in response.get("responseData", []):
        if node.get("moduleType") == "chatNode" and not reasoning:
            reasoning = str(node.get("reasoningText") or "")
    return output.strip(), reasoning.strip()


def extract_structured_evaluation(response: dict[str, Any]) -> dict[str, Any]:
    def is_structured_result(value: Any) -> bool:
        return isinstance(value, dict) and any(key in value for key in ("score", "score_text", "verdict", "summary", "subscores", "needs_review"))

    def maybe_return(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            for key in ("评估结构化分数", "结构化评估分数"):
                nested = value.get(key)
                if is_structured_result(nested):
                    return nested
            if is_structured_result(value):
                return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except Exception:
                return None
            return maybe_return(parsed)
        return None

    for value in (response.get("newVariables") or {}).values():
        parsed = maybe_return(value)
        if parsed is not None:
            return parsed

    for node in response.get("responseData", []):
        if not isinstance(node, dict) or node.get("moduleType") != "contentExtract":
            continue
        extract_result = node.get("extractResult")
        if isinstance(extract_result, dict):
            for key in ("评估结构化分数", "结构化评估分数"):
                value = extract_result.get(key)
                parsed = maybe_return(value)
                if parsed is not None:
                    return parsed
        for key in ("评估结构化分数", "结构化评估分数", "fields"):
            value = node.get(key)
            parsed = maybe_return(value)
            if parsed is not None:
                return parsed
        error_text = str(node.get("errorText") or node.get("system_error_text") or "").strip()
        if error_text:
            raise RuntimeError(error_text)

    output_text, _ = extract_plugin_text(response)
    if output_text:
        try:
            parsed = json.loads(output_text)
        except Exception as exc:
            raise RuntimeError(f"structured evaluation returned non-json output: {output_text[:200]}") from exc
        if is_structured_result(parsed):
            return parsed
    error_text = str(response.get("error") or "").strip()
    if error_text:
        raise RuntimeError(error_text)
    raise RuntimeError("structured evaluation returned no structured result")


def with_review_background(prompt: str, fault_scene: str = "", graph_material: str = "") -> str:
    background_parts: list[str] = []
    if fault_scene:
        background_parts.append(f"【故障与场景背景】\n{fault_scene}")
    if graph_material:
        background_parts.append(f"【图谱检索背景】\n{graph_material}")
    if not background_parts:
        return prompt
    return prompt + "\n\n" + "\n\n".join(background_parts)


def run_format_review_sync(prompt: str, content: str, fault_scene: str = "", graph_material: str = "") -> dict[str, Any]:
    prompt = with_review_background(prompt, fault_scene, graph_material)
    payload = {
        "stream": False,
        "detail": True,
        "variables": {
            "提示词": prompt,
            "当前需求": content,
        },
    }
    req = Request(
        FORMAT_REVIEW_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_format_review_key()}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"format review HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"format review URL error: {exc}")
    output_text, reasoning_text = extract_plugin_text(body)
    return {
        "output_text": output_text,
        "reasoning_text": reasoning_text,
        "raw": body,
    }


def run_structured_evaluation_sync(
    *,
    evaluation_text: str,
    question: str = "",
    question_group: str = "",
    experiment_group: str = "",
) -> dict[str, Any]:
    payload = {
        "stream": False,
        "detail": True,
        "variables": {
            "评估原文": evaluation_text,
            "实验组名称": experiment_group,
            "题目分组": question_group,
            "原始用户问题": question,
        },
    }
    req = Request(
        STRUCTURED_EVALUATION_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_structured_evaluation_key()}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urlopen(req, timeout=180) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"structured evaluation HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"structured evaluation URL error: {exc}")
    return extract_structured_evaluation(body)


def stream_format_review(handler: BaseHTTPRequestHandler, prompt: str, content: str, mode: str, fault_scene: str = "", graph_material: str = "") -> dict[str, Any]:
    prompt = with_review_background(prompt, fault_scene, graph_material)
    payload = {
        "stream": True,
        "detail": True,
        "variables": {
            "提示词": prompt,
            "当前需求": content,
        },
    }
    req = Request(
        FORMAT_REVIEW_PLUGIN_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {read_format_review_key()}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "text/event-stream",
        },
    )

    send_sse(handler, "quality_status", {"mode": mode, "status": "started"})

    reasoning_text = ""
    output_text = ""
    event_name = ""
    data_lines: list[str] = []
    seen_reasoning = False
    seen_output = False

    def flush_event() -> None:
        nonlocal event_name, data_lines, reasoning_text, output_text, seen_reasoning, seen_output
        if not event_name and not data_lines:
            return
        payload_text = "\n".join(data_lines).strip()
        if event_name == "answer" and payload_text and payload_text != "[DONE]":
            try:
                payload_obj = json.loads(payload_text)
            except Exception:
                payload_obj = {}
            if isinstance(payload_obj, dict):
                choices = payload_obj.get("choices", [])
                if isinstance(choices, list) and choices:
                    delta = choices[0].get("delta", {}) if isinstance(choices[0], dict) else {}
                    reasoning_chunk = str(delta.get("reasoning_content") or "")
                    text_chunk = str(delta.get("content") or "")
                    if reasoning_chunk:
                        reasoning_text += reasoning_chunk
                        if not seen_reasoning:
                            seen_reasoning = True
                            send_sse(handler, "quality_status", {"mode": mode, "status": "thinking"})
                        send_sse(handler, "quality_reasoning_chunk", {"mode": mode, "chunk": reasoning_chunk})
                    if text_chunk:
                        output_text += text_chunk
                        if not seen_output:
                            seen_output = True
                            send_sse(handler, "quality_status", {"mode": mode, "status": "generating"})
                        send_sse(handler, "quality_output_chunk", {"mode": mode, "chunk": text_chunk})
        event_name = ""
        data_lines = []

    try:
        with urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
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
        raise RuntimeError(f"format review HTTP {exc.code}: {detail[:400]}")
    except URLError as exc:
        raise RuntimeError(f"format review URL error: {exc}")

    send_sse(
        handler,
        "quality_done",
        {
            "mode": mode,
            "status": "done",
            "output_text": output_text,
            "reasoning_text": reasoning_text,
        },
    )
    return {"output_text": output_text, "reasoning_text": reasoning_text}
