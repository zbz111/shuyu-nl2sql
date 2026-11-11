"""大模型调用：Ollama（默认）与 OpenAI 兼容接口。"""
from __future__ import annotations

from collections.abc import Iterator

import httpx

from ..config import settings


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict], temperature: float | None = None, max_tokens: int | None = None) -> tuple[str, int]:
    temp = settings.temperature if temperature is None else temperature
    limit = settings.max_tokens if max_tokens is None else max_tokens
    if settings.llm_provider == "openai":
        url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        payload = {
            "model": settings.openai_chat_model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": limit,
        }
    else:
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        headers = {}
        payload = {
            "model": settings.ollama_chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temp, "num_predict": limit},
        }

    try:
        with httpx.Client(timeout=httpx.Timeout(180, connect=5)) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                hint = {
                    401: "API Key 无效或已失效，请更新 .env 的 OPENAI_API_KEY 后重启服务。",
                    402: "账户余额不足。",
                    403: "API Key 没有该模型权限。",
                    404: "模型名不存在，请检查 OPENAI_CHAT_MODEL。",
                    429: "请求被限流，请稍后重试。",
                }.get(resp.status_code)
                if hint:
                    raise LLMError(f"模型服务返回 {resp.status_code}：{hint}")
                raise LLMError(f"模型服务返回 {resp.status_code}：{resp.text[:200]}")
            data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"模型服务不可达：{exc}") from exc

    if settings.llm_provider == "openai":
        content = data["choices"][0]["message"]["content"]
        tokens = int(data.get("usage", {}).get("total_tokens", 0))
    else:
        content = data.get("message", {}).get("content", "")
        tokens = int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
    return content, tokens


def stream_chat(messages: list[dict]) -> Iterator[str]:  # 预留：流式结论
    content, _ = chat(messages)
    yield content


def health() -> dict:
    if settings.llm_provider == "openai":
        return {
            "provider": "openai",
            "model": settings.openai_chat_model,
            "ok": bool(settings.openai_api_key),
        }
    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            return {
                "provider": "ollama",
                "model": settings.ollama_chat_model,
                "ok": resp.status_code == 200 and settings.ollama_chat_model in models,
                "models": models,
            }
    except httpx.HTTPError:
        return {"provider": "ollama", "model": settings.ollama_chat_model, "ok": False}
