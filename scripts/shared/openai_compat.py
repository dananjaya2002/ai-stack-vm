import json
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests
from fastapi.responses import StreamingResponse


def upstream_payload(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    stream: bool,
) -> Dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }


def buffered_completion(
    url: str,
    payload: Dict[str, Any],
    proxy_model: str,
    timeout: int = 300,
    content_transform: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    response = requests.post(url, json={**payload, "stream": False}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    data["model"] = proxy_model
    if content_transform:
        for choice in data.get("choices", []):
            message = choice.get("message") or {}
            if isinstance(message.get("content"), str):
                message["content"] = content_transform(message["content"])
    return data


def _stream_events(
    response: requests.Response,
    completion_id: str,
    proxy_model: str,
    content_transform: Optional[Callable[[str], str]] = None,
) -> Iterable[str]:
    try:
        if content_transform:
            raw_content = ""
            emitted_length = 0
            last_event: Dict[str, Any] = {}
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8", errors="replace")
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                try:
                    event = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                last_event = event
                for choice in event.get("choices", []):
                    content = (choice.get("delta") or {}).get("content")
                    if isinstance(content, str):
                        raw_content += content

                # Keep a short tail so markers split across upstream tokens can
                # be rewritten before any part of them reaches the client.
                transformed = content_transform(raw_content)
                stable_length = max(0, len(transformed) - 256)
                if stable_length > emitted_length:
                    output = transformed[emitted_length:stable_length]
                    emitted_length = stable_length
                    output_event = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": event.get("created") or int(time.time()),
                        "model": proxy_model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": output},
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output_event, ensure_ascii=False)}\n\n"

            transformed = content_transform(raw_content)
            remaining = transformed[emitted_length:]
            if remaining:
                output_event = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": last_event.get("created") or int(time.time()),
                    "model": proxy_model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": remaining},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(output_event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="replace")
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            data_text = line[5:].strip()
            if data_text == "[DONE]":
                break
            try:
                event = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            event["id"] = completion_id
            event["object"] = "chat.completion.chunk"
            event["created"] = event.get("created") or int(time.time())
            event["model"] = proxy_model
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    finally:
        response.close()


def streaming_completion(
    url: str,
    payload: Dict[str, Any],
    proxy_model: str,
    id_prefix: str,
    timeout: int = 300,
    content_transform: Optional[Callable[[str], str]] = None,
) -> StreamingResponse:
    response = requests.post(
        url,
        json={**payload, "stream": True},
        stream=True,
        timeout=timeout,
    )
    response.raise_for_status()
    completion_id = f"{id_prefix}-{uuid.uuid4()}"
    return StreamingResponse(
        _stream_events(response, completion_id, proxy_model, content_transform),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def proxy_completion(
    url: str,
    payload: Dict[str, Any],
    proxy_model: str,
    id_prefix: str,
    stream: bool,
    timeout: int = 300,
    content_transform: Optional[Callable[[str], str]] = None,
) -> Any:
    if stream:
        return streaming_completion(
            url,
            payload,
            proxy_model,
            id_prefix,
            timeout,
            content_transform,
        )
    return buffered_completion(url, payload, proxy_model, timeout, content_transform)
