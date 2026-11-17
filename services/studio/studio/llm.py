"""OpenRouter: the live model list (with prices) and JSON chat completions with real cost from `usage`."""
import json
import os
import re
import time

import httpx

BASE = "https://openrouter.ai/api/v1"
_models: tuple[float, list[dict]] | None = None


class LLMError(RuntimeError):
    """`cost` is what the failed call still spent (paid empty replies, a reply that was not JSON)."""

    def __init__(self, msg: str, cost: float = 0.0):
        super().__init__(msg)
        self.cost = cost


def key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")


def models() -> list[dict]:
    """Text models from OpenRouter (public endpoint, cached 30 min), newest first, with $ per million tokens."""
    global _models
    if _models and time.monotonic() - _models[0] < 1800:
        return _models[1]
    r = httpx.get(f"{BASE}/models", timeout=30)
    r.raise_for_status()
    out = []
    for m in r.json().get("data", []):
        arch = m.get("architecture") or {}
        if "text" not in (arch.get("output_modalities") or ["text"]):
            continue
        p = m.get("pricing") or {}
        try:
            pin, pout = float(p.get("prompt") or 0) * 1e6, float(p.get("completion") or 0) * 1e6
        except ValueError:
            continue
        if pin < 0 or pout < 0:          # router pseudo-models report -1
            continue
        out.append({"id": m["id"], "name": m.get("name") or m["id"], "context": m.get("context_length") or 0,
                    "in_per_m": round(pin, 4), "out_per_m": round(pout, 4), "created": m.get("created") or 0,
                    "provider": m["id"].split("/")[0]})
    out.sort(key=lambda m: -m["created"])
    _models = (time.monotonic(), out)
    return out


def balance() -> float | None:
    """Credits left on the OpenRouter account in USD (None if it can't be read)."""
    if not key():
        return None
    try:
        r = httpx.get(f"{BASE}/credits", headers={"Authorization": f"Bearer {key()}"}, timeout=10)
        d = r.json().get("data") or {}
        return round(float(d.get("total_credits") or 0) - float(d.get("total_usage") or 0), 4)
    except (httpx.HTTPError, ValueError, TypeError):
        return None


def price(model_id: str) -> dict | None:
    try:
        return next((m for m in models() if m["id"] == model_id), None)
    except httpx.HTTPError:
        return None


def estimate_usd(model_id: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    p = price(model_id)
    if not p:
        return None
    return round((prompt_tokens * p["in_per_m"] + completion_tokens * p["out_per_m"]) / 1e6, 4)


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start > 0:
        text = text[start:]
    return json.loads(text)


def chat(model: str, messages: list[dict], *, temperature: float = 0.4, max_tokens: int = 16000,
         json_mode: bool = True, timeout: float = 600) -> tuple[str, float, dict]:
    """One completion. Returns (text, cost_usd, usage). Retries 429/5xx twice."""
    if not key():
        raise LLMError("OPENROUTER_API_KEY is not set in .env")
    body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens,
            "usage": {"include": True}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {key()}", "X-Title": "EduVid Studio"}
    last = None
    spent = 0.0                                    # empty replies are billed too: count them
    for attempt in range(3):
        try:
            r = httpx.post(f"{BASE}/chat/completions", json=body, headers=headers, timeout=timeout)
        except httpx.HTTPError as e:
            last = f"network: {e}"
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 400 and json_mode and "response_format" in r.text:
            body.pop("response_format", None)          # some providers reject json mode: the prompt asks for JSON
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"{r.status_code}: {r.text[:300]}"
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 402:
            raise LLMError("OpenRouter credit is used up for this model (HTTP 402). Add credits at "
                           "https://openrouter.ai/settings/credits, or pick a cheaper or free model.", spent)
        if r.status_code >= 400:
            raise LLMError(f"OpenRouter {r.status_code}: {r.text[:500]}", spent)
        data = r.json()
        if data.get("error"):
            raise LLMError(f"OpenRouter error: {str(data['error'])[:500]}", spent)
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        if cost is None:
            cost = estimate_usd(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)) or 0.0
        spent += float(cost)
        if not text.strip():
            last = f"empty reply (finish_reason={choice.get('finish_reason')})"
            continue
        return text, spent, usage
    raise LLMError(f"OpenRouter failed after retries: {last}", spent)


def chat_json(model: str, messages: list[dict], **kw):
    """chat() whose reply must be JSON. One repair round if it isn't. Returns (obj, cost_usd)."""
    text, cost, _ = chat(model, messages, **kw)
    try:
        return _extract_json(text), cost
    except ValueError as e:
        fix = messages + [{"role": "assistant", "content": text[:20000]},
                          {"role": "user", "content": f"That was not valid JSON ({e}). Reply with the complete JSON "
                                                      "object only, no prose, no code fences."}]
        try:
            text2, cost2, _ = chat(model, fix, **kw)
        except LLMError as e2:
            raise LLMError(str(e2), cost + e2.cost) from e2
        try:
            return _extract_json(text2), cost + cost2
        except ValueError as e2:
            raise LLMError(f"the model did not reply with valid JSON, even when asked again ({e2})", cost + cost2)
