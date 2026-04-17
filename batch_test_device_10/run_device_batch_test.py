#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://localhost:3000/api"
DEFAULT_API_KEY_FILE = REPO_ROOT / "api" / "testkey.txt"
DEFAULT_CASES_FILE = Path(__file__).resolve().parent / "questions_10_device.tsv"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
RAW_DIR = OUTPUT_DIR / "raw"


DEVICE_ALIASES = {
    "llmkg_breaker": "断路器",
    "llmkg_test": "断路器",
    "llmkg_transmission_line": "输电线路",
    "llmkg_transformer": "变压器",
    "llmkg_mutual": "互感器",
}


DEVICE_KEYWORDS = {
    "断路器": [
        "断路器",
        "触头",
        "合分闸",
        "灭弧",
        "sf6",
        "六氟化硫",
        "操动机构",
        "导电连接",
        "开断",
    ],
    "输电线路": [
        "输电线路",
        "线路",
        "覆冰",
        "舞动",
        "风偏",
        "雷击",
        "污闪",
        "鸟害",
        "外力破坏",
    ],
    "变压器": [
        "变压器",
        "瓦斯继电器",
        "绕组",
        "油位",
        "分接",
        "有载调压",
        "铁芯",
        "套管",
    ],
    "互感器": [
        "互感器",
        "ct",
        "pt",
        "二次回路",
        "采样",
        "计量异常",
        "保护判据",
    ],
}


def read_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"API key file is empty: {path}")
    return key


def parse_case_line(line: str) -> Tuple[str, str]:
    text = line.strip()
    if not text:
        return "", ""
    if "\t" in text:
        expected, question = text.split("\t", 1)
        return expected.strip(), question.strip()
    parts = re.split(r"\s*\|\s*", text, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", text


def load_cases(path: Path) -> List[Dict[str, str]]:
    cases: List[Dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        expected, question = parse_case_line(raw)
        if not question:
            continue
        if expected not in DEVICE_KEYWORDS:
            raise RuntimeError(f"Invalid expected device in line: {raw}")
        cases.append({"expected_device": expected, "question": question})
    return cases


def post_json(url: str, payload: Dict, api_key: str, timeout: int) -> Dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return parse_sse_response(body)


def parse_sse_response(body: str) -> Dict:
    response: Dict = {}
    answer_parts: List[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if isinstance(obj, list):
            response["responseData"] = obj
            continue
        if not isinstance(obj, dict):
            continue
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0]
            if isinstance(c0, dict):
                delta = c0.get("delta", {})
                if isinstance(delta, dict):
                    piece = delta.get("content")
                    if isinstance(piece, str):
                        answer_parts.append(piece)
        for k in ("responseData", "newVariables", "error", "id", "model", "usage", "choices"):
            if k in obj:
                response[k] = obj[k]
    if answer_parts:
        content = "".join(answer_parts)
        has_full_message = False
        cur_choices = response.get("choices")
        if isinstance(cur_choices, list) and cur_choices:
            c0 = cur_choices[0]
            if isinstance(c0, dict) and isinstance(c0.get("message"), dict):
                has_full_message = True
        if not has_full_message:
            response["choices"] = [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                    "index": 0,
                }
            ]
    if not response:
        raise json.JSONDecodeError("Unable to parse SSE response", body, 0)
    return response


def extract_answer(response: Dict) -> str:
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
    return ""


def iter_extract_dicts(response: Dict):
    response_data = response.get("responseData", [])
    if not isinstance(response_data, list):
        return
    for node in response_data:
        if not isinstance(node, dict):
            continue
        ext = node.get("extractResult")
        if isinstance(ext, dict):
            yield ext
    nv = response.get("newVariables")
    if isinstance(nv, dict):
        yield nv


def score_by_keywords(text: str) -> str:
    lower = text.lower()
    scores = {d: 0 for d in DEVICE_KEYWORDS}
    for device, kws in DEVICE_KEYWORDS.items():
        for kw in kws:
            if kw in lower:
                scores[device] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def extract_device(response: Dict, answer: str) -> str:
    # 1) structured fields
    keys = [
        "故障设备",
        "设备",
        "device",
        "device_name",
        "deviceName",
        "devicespace",
        "space",
    ]
    for obj in iter_extract_dicts(response):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                s = v.strip()
                if s in DEVICE_KEYWORDS:
                    return s
                if s in DEVICE_ALIASES:
                    return DEVICE_ALIASES[s]
                scored = score_by_keywords(s)
                if scored:
                    return scored

    # 2) responseData/full response text
    blob = json.dumps(response.get("responseData", []), ensure_ascii=False)
    scored_blob = score_by_keywords(blob)
    if scored_blob:
        return scored_blob

    # 3) final answer text
    scored_ans = score_by_keywords(answer or "")
    if scored_ans:
        return scored_ans
    return ""


def one_case(
    idx: int,
    expected_device: str,
    question: str,
    endpoint: str,
    api_key: str,
    timeout: int,
    raw_dir: Path,
    chat_id: str,
) -> Dict:
    payload = {
        "chatId": chat_id,
        "stream": True,
        "detail": True,
        "customUid": "batch-test-device-10",
        "messages": [{"role": "user", "content": question}],
    }
    start = time.time()
    status = "ok"
    err = ""
    response: Dict = {}
    try:
        response = post_json(endpoint, payload, api_key, timeout=timeout)
    except HTTPError as e:
        status = "http_error"
        err = f"HTTP {e.code}"
        try:
            body = e.read().decode("utf-8", errors="replace")
            response = {"_error_body": body}
        except Exception:
            pass
    except URLError as e:
        status = "url_error"
        err = str(e)
    except Exception as e:  # noqa: BLE001
        status = "exception"
        err = str(e)

    elapsed = round(time.time() - start, 3)
    answer = extract_answer(response) if response else ""
    predicted_device = extract_device(response, answer) if response else ""
    is_correct = status == "ok" and predicted_device == expected_device

    raw_payload = {
        "index": idx,
        "expected_device": expected_device,
        "question": question,
        "request": payload,
        "status": status,
        "elapsed_sec": elapsed,
        "predicted_device": predicted_device,
        "is_correct": is_correct,
        "response": response,
    }
    raw_file = raw_dir / f"{idx:02d}.json"
    raw_file.write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "index": idx,
        "expected_device": expected_device,
        "predicted_device": predicted_device,
        "is_correct": is_correct,
        "question": question,
        "status": status,
        "elapsed_sec": elapsed,
        "final_error": err,
        "answer": answer,
    }


def write_report(results: List[Dict], output_txt: Path) -> None:
    total = len(results)
    ok = sum(1 for x in results if x["status"] == "ok")
    correct = sum(1 for x in results if x["is_correct"])
    acc = round(correct * 100.0 / total, 2) if total else 0.0

    expected_stats = {k: 0 for k in DEVICE_KEYWORDS}
    hit_stats = {k: 0 for k in DEVICE_KEYWORDS}
    for r in results:
        expected_stats[r["expected_device"]] += 1
        if r["is_correct"]:
            hit_stats[r["expected_device"]] += 1

    lines: List[str] = []
    lines.append(f"Batch Test Time: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Total Cases: {total}")
    lines.append(f"HTTP Success: {ok}")
    lines.append(f"Correct: {correct}")
    lines.append(f"Accuracy: {acc}%")
    lines.append("-" * 88)
    lines.append("Per-Device Accuracy:")
    for d in DEVICE_KEYWORDS:
        n = expected_stats[d]
        h = hit_stats[d]
        ratio = round(h * 100.0 / n, 2) if n else 0.0
        lines.append(f"  {d}: {h}/{n} ({ratio}%)")
    lines.append("-" * 88)

    for r in results:
        lines.append(f"[{r['index']:02d}] {r['question']}")
        lines.append(
            f"  expected={r['expected_device']} predicted={r['predicted_device']} correct={r['is_correct']}"
        )
        lines.append(f"  status={r['status']} elapsed={r['elapsed_sec']}s")
        ans = (r.get("answer") or "").replace("\n", " ").strip()
        lines.append(f"  answer={ans[:300]}")
        lines.append("")

    output_txt.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="FastGPT 10-case device recognition test")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--cases-file", type=Path, default=DEFAULT_CASES_FILE)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--chat-mode", choices=["shared", "per_case"], default="per_case")
    parser.add_argument("--chat-id", default="")
    args = parser.parse_args()

    endpoint = args.base_url.rstrip("/") + "/v1/chat/completions"
    api_key = read_key(args.api_key_file)
    cases = load_cases(args.cases_file)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.chat_mode == "shared":
        shared_chat_id = args.chat_id.strip() or f"batch-device-shared-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    else:
        shared_chat_id = ""

    print(f"[INFO] Endpoint: {endpoint}")
    print(f"[INFO] Cases: {len(cases)}")
    print(f"[INFO] Chat Mode: {args.chat_mode}")
    if shared_chat_id:
        print(f"[INFO] Shared Chat ID: {shared_chat_id}")

    results: List[Dict] = []
    for i, case in enumerate(cases, start=1):
        chat_id = shared_chat_id if args.chat_mode == "shared" else f"batch-device-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i:02d}"
        item = one_case(
            idx=i,
            expected_device=case["expected_device"],
            question=case["question"],
            endpoint=endpoint,
            api_key=api_key,
            timeout=args.timeout,
            raw_dir=RAW_DIR,
            chat_id=chat_id,
        )
        results.append(item)
        print(
            f"[PROGRESS] {i}/{len(cases)} "
            f"status={item['status']} "
            f"expected={item['expected_device']} "
            f"predicted={item['predicted_device'] or '-'} "
            f"correct={item['is_correct']} "
            f"cost={item['elapsed_sec']}s",
            flush=True,
        )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_file = OUTPUT_DIR / f"device_results_{ts}.txt"
    write_report(results, txt_file)

    correct = sum(1 for x in results if x["is_correct"])
    acc = round(correct * 100.0 / len(results), 2) if results else 0.0
    print(f"[DONE] Report: {txt_file}")
    print(f"[DONE] Raw Dir: {RAW_DIR}")
    print(f"[DONE] Accuracy: {correct}/{len(results)} = {acc}%")


if __name__ == "__main__":
    main()

