#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FastGPT 批量故障描述测试（滚动并发）
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://localhost:3000/api"
DEFAULT_API_KEY_FILE = REPO_ROOT / "api" / "testkey.txt"
DEFAULT_QUESTIONS_FILE = Path(__file__).resolve().parent / "questions_34.txt"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
RAW_DIR = OUTPUT_DIR / "raw"


def normalize_question(line: str) -> str:
    line = line.strip()
    # 去掉前缀编号，如 "1. " / "12、"
    return re.sub(r"^\s*\d+\s*[\.、]\s*", "", line).strip()


def load_questions(path: Path) -> List[str]:
    questions: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = normalize_question(raw)
        if text:
            questions.append(text)
    return questions


def read_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"API key 文件为空: {path}")
    return key


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
    """
    解析 stream=true 的 SSE 文本响应，尽量还原为统一的 response dict。
    """
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
            # 某些流事件会直接返回 responseData 数组
            response["responseData"] = obj
            continue
        if not isinstance(obj, dict):
            continue

        # 增量答案分片
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0]
            if isinstance(c0, dict):
                delta = c0.get("delta", {})
                if isinstance(delta, dict):
                    piece = delta.get("content")
                    if isinstance(piece, str):
                        answer_parts.append(piece)

        # 可能出现完整对象片段（detail=true 常见）
        for k in ("responseData", "newVariables", "error", "id", "model", "usage", "choices"):
            if k in obj:
                response[k] = obj[k]

    # 若没有完整 choices.message，则用增量片段拼接一个
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


def extract_matched_l2(response: Dict) -> str:
    for node in response.get("responseData", []):
        ext = node.get("extractResult")
        if isinstance(ext, dict):
            for k in ("故障二级节点", "二级故障名称", "l2_name"):
                v = ext.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return ""


def extract_final_error(response: Dict) -> str:
    # 优先取顶层 error
    if isinstance(response.get("error"), str) and response["error"]:
        return response["error"]
    # 其次找最后一个 chatNode 的 errorText
    chat_nodes = [
        n
        for n in response.get("responseData", [])
        if n.get("moduleType") == "chatNode"
    ]
    if chat_nodes:
        err = chat_nodes[-1].get("errorText", "")
        if isinstance(err, str):
            return err
    return ""


def extract_answer(response: Dict) -> str:
    choices = response.get("choices", [])
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
    return ""


def one_case(
    idx: int,
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
        "customUid": "batch-test-34",
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
    matched_l2 = extract_matched_l2(response) if response else ""
    final_error = extract_final_error(response) if response else err
    answer = extract_answer(response) if response else ""

    # 保存原始响应
    raw_payload = {
        "index": idx,
        "question": question,
        "request": payload,
        "status": status,
        "elapsed_sec": elapsed,
        "response": response,
    }
    raw_file = raw_dir / f"{idx:02d}.json"
    raw_file.write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "index": idx,
        "question": question,
        "status": status,
        "elapsed_sec": elapsed,
        "matched_l2": matched_l2,
        "final_error": final_error,
        "answer": answer,
        "chat_id": response.get("id", ""),
    }


def rolling_run(
    questions: List[str],
    endpoint: str,
    api_key: str,
    timeout: int,
    max_concurrency: int,
    raw_dir: Path,
    chat_mode: str,
    shared_chat_id: str,
) -> List[Dict]:
    results: List[Dict] = []
    lock = threading.Lock()
    pending = iter(list(enumerate(questions, start=1)))
    total_cases = len(questions)
    started = time.time()

    def submit_next(executor, future_map):
        try:
            i, q = next(pending)
        except StopIteration:
            return
        if chat_mode == "shared":
            cid = shared_chat_id
        else:
            cid = f"batch-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i:02d}"
        fut = executor.submit(one_case, i, q, endpoint, api_key, timeout, raw_dir, cid)
        future_map[fut] = (i, q)

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_map = {}
        for _ in range(max_concurrency):
            submit_next(executor, future_map)
        while future_map:
            done, _ = wait(future_map.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                i, _q = future_map.pop(fut)
                try:
                    item = fut.result()
                except Exception as e:  # noqa: BLE001
                    item = {
                        "index": i,
                        "question": "",
                        "status": "worker_exception",
                        "elapsed_sec": 0,
                        "matched_l2": "",
                        "final_error": str(e),
                        "answer": "",
                        "chat_id": "",
                    }
                with lock:
                    results.append(item)
                    completed = len(results)
                    q_preview = (item.get("question") or "").replace("\n", " ").strip()
                    if len(q_preview) > 24:
                        q_preview = q_preview[:24] + "..."
                    matched = item.get("matched_l2") or "-"
                    ans_non_empty = "Y" if (item.get("answer") or "").strip() else "N"
                    ferr = item.get("final_error") or "-"
                    total_elapsed = round(time.time() - started, 1)
                    print(
                        f"[PROGRESS] {completed}/{total_cases} "
                        f"idx={item.get('index', 0):02d} "
                        f"status={item.get('status', '-') } "
                        f"cost={item.get('elapsed_sec', 0)}s "
                        f"matched={matched} "
                        f"answer={ans_non_empty} "
                        f"err={ferr} "
                        f"total={total_elapsed}s "
                        f"q={q_preview}",
                        flush=True,
                    )
                submit_next(executor, future_map)

    return sorted(results, key=lambda x: x["index"])


def write_txt_report(results: List[Dict], output_txt: Path) -> None:
    ok = sum(1 for x in results if x["status"] == "ok")
    answer_non_empty = sum(1 for x in results if (x.get("answer") or "").strip())
    lines: List[str] = []
    lines.append(f"Batch Test Time: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Total Cases: {len(results)}")
    lines.append(f"HTTP Success: {ok}")
    lines.append(f"Final Answer Non-Empty: {answer_non_empty}")
    lines.append("-" * 88)

    for r in results:
        lines.append(f"[{r['index']:02d}] {r['question']}")
        lines.append(
            f"  status={r['status']} elapsed={r['elapsed_sec']}s chatId={r.get('chat_id','')}"
        )
        lines.append(f"  matched_l2={r.get('matched_l2','')}")
        lines.append(f"  final_error={r.get('final_error','')}")
        ans = (r.get("answer") or "").replace("\n", " ").strip()
        lines.append(f"  answer={ans[:300]}")
        lines.append("")

    output_txt.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FastGPT 34条故障描述滚动并发测试（上限10）"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key-file", type=Path, default=DEFAULT_API_KEY_FILE)
    parser.add_argument("--questions-file", type=Path, default=DEFAULT_QUESTIONS_FILE)
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument(
        "--chat-mode",
        choices=["shared", "per_case"],
        default="shared",
        help="shared=所有问题复用同一个chatId（连续对话）；per_case=每题独立chatId",
    )
    parser.add_argument(
        "--chat-id",
        default="",
        help="当 chat-mode=shared 时可指定固定 chatId；为空则自动生成",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="仅运行前N条问题（0表示全部）",
    )
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    endpoint = args.base_url.rstrip("/") + "/v1/chat/completions"
    api_key = read_key(args.api_key_file)
    questions = load_questions(args.questions_file)
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]

    if len(questions) != 34:
        print(f"[WARN] 当前问题条数为 {len(questions)}，不是 34。")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    max_concurrency = args.max_concurrency
    if args.chat_mode == "shared" and max_concurrency > 1:
        print(
            "[WARN] shared chat mode 下并发会破坏上下文顺序，已自动降为 1。"
        )
        max_concurrency = 1

    if args.chat_mode == "shared":
        shared_chat_id = (
            args.chat_id
            if args.chat_id.strip()
            else f"batch-shared-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
    else:
        shared_chat_id = ""

    print(f"[INFO] Endpoint: {endpoint}")
    print(f"[INFO] Questions: {len(questions)}")
    print(f"[INFO] Chat Mode: {args.chat_mode}")
    if shared_chat_id:
        print(f"[INFO] Shared Chat ID: {shared_chat_id}")
    print(f"[INFO] Max Concurrency: {max_concurrency}")

    results = rolling_run(
        questions=questions,
        endpoint=endpoint,
        api_key=api_key,
        timeout=args.timeout,
        max_concurrency=max_concurrency,
        raw_dir=RAW_DIR,
        chat_mode=args.chat_mode,
        shared_chat_id=shared_chat_id,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_file = OUTPUT_DIR / f"results_{ts}.txt"
    write_txt_report(results, txt_file)

    print(f"[DONE] Report: {txt_file}")
    print(f"[DONE] Raw Dir: {RAW_DIR}")


if __name__ == "__main__":
    main()
