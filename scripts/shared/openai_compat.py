import json
import time
import uuid
from typing import Any, Dict, Iterable, List

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
) -> Dict[str, Any]:
    response = requests.post(url, json={**payload, "stream": False}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    data["model"] = proxy_model
    return data


def _stream_events(
    response: requests.Response,
    completion_id: str,
    proxy_model: str,
) -> Iterable[str]:
    try:
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
        _stream_events(response, completion_id, proxy_model),
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
) -> Any:
    if stream:
        return streaming_completion(url, payload, proxy_model, id_prefix, timeout)
    return buffered_completion(url, payload, proxy_model, timeout)
