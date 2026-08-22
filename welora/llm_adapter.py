"""
Welora P1-E4 — LLM adapter (after Pre-Rule only)

Hard rule: NEVER call this on guardrail_result == deny.
Env:
  WELORA_LLM_PROVIDER = stub | openai | xai | anthropic
  WELORA_LLM_API_KEY  = ...
  WELORA_LLM_MODEL    = optional model name
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Optional


SYSTEM_BASE = """Bạn là Welora CFO Agent (advisory-only).
Nguyên tắc cứng:
- An Toàn trước: quỹ khẩn cấp ≥ 3 tháng, không khuyến khích phá quỹ để đầu tư.
- Không cam kết lợi suất % cố định / “chắc lời”.
- Không ra lệnh mua/bán ticker cụ thể như khuyến nghị đầu tư cá nhân hóa pháp lý.
- Không bypass Cổng An Toàn.
- Tiếng Việt, rõ ràng, tôn trọng user.
"""


def stub_llm(system: str, message: str) -> str:
    return (
        f"[stub-llm] {system.split(chr(10))[0][:80]}…\n\n"
        f"Tôi đã nhận: «{message[:160]}». "
        "Đây là phản hồi advisory stub (chưa gọi model thật). "
        "Khi Cổng An Toàn đã đạt, bạn có thể hỏi khung rủi ro, Goal tiết kiệm, "
        "hoặc nguyên tắc phân bổ — không phải lệnh all-in."
    )


def _http_json(url: str, headers: dict, payload: dict, timeout: float = 45.0) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def openai_compatible_llm(
    system: str,
    message: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
) -> str:
    data = _http_json(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        payload={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "temperature": 0.3,
        },
    )
    return data["choices"][0]["message"]["content"]


def make_llm_callable() -> Optional[Callable[[str, str], str]]:
    provider = (os.environ.get("WELORA_LLM_PROVIDER") or "stub").lower().strip()
    if provider in ("", "none", "off", "rule_only"):
        return None
    if provider == "stub":
        return stub_llm

    api_key = os.environ.get("WELORA_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        return stub_llm

    model = os.environ.get("WELORA_LLM_MODEL") or ""
    if provider == "openai":
        model = model or "gpt-4o-mini"
        base = os.environ.get("WELORA_LLM_BASE_URL") or "https://api.openai.com/v1"

        def _call(system: str, message: str) -> str:
            return openai_compatible_llm(
                SYSTEM_BASE + "\n" + system,
                message,
                base_url=base,
                api_key=api_key,
                model=model,
            )

        return _call

    if provider in ("xai", "grok"):
        model = model or "grok-2-latest"
        base = os.environ.get("WELORA_LLM_BASE_URL") or "https://api.x.ai/v1"

        def _call(system: str, message: str) -> str:
            return openai_compatible_llm(
                SYSTEM_BASE + "\n" + system,
                message,
                base_url=base,
                api_key=api_key,
                model=model,
            )

        return _call

    if provider == "anthropic":
        model = model or "claude-3-5-haiku-latest"
        base = os.environ.get("WELORA_LLM_BASE_URL") or "https://api.anthropic.com/v1"

        def _call(system: str, message: str) -> str:
            req = urllib.request.Request(
                f"{base.rstrip('/')}/messages",
                data=json.dumps(
                    {
                        "model": model,
                        "max_tokens": 800,
                        "system": SYSTEM_BASE + "\n" + system,
                        "messages": [{"role": "user", "content": message}],
                    }
                ).encode("utf-8"),
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            parts = data.get("content") or []
            texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
            return "\n".join(texts) or str(data)

        return _call

    return stub_llm


def safe_call_llm(
    call_llm: Optional[Callable[[str, str], str]],
    system: str,
    message: str,
) -> tuple[str, str]:
    if not call_llm:
        return "", "none"
    try:
        return call_llm(system, message), "llm"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, OSError) as e:
        return (
            f"Tạm thời không gọi được model ({type(e).__name__}). "
            "Tôi vẫn có thể hỗ trợ bằng khung nguyên tắc Welora — "
            "bạn muốn xem Cổng An Toàn hay Goal quỹ?"
        ), "llm_error"
