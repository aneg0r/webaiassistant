"""Normalized LLM layer — dispatch by model name prefix."""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app import config

T = TypeVar("T", bound=BaseModel)

_gemini_client: Optional[Any] = None
_gemini_lock = threading.Lock()


def generate(prompt: str, model: Optional[str] = None) -> str:
    """Call the appropriate LLM backend from the model name prefix."""
    m = (model or config.LLM_MODEL).strip()
    ml = m.lower()
    if ml.startswith("gemini"):
        return _generate_gemini(prompt, m)
    if ml.startswith("mistral") or ml.startswith("open-mistral") or ml.startswith(
        "ministral"
    ) or ml.startswith("codestral"):
        return _generate_mistral(prompt, m)
    if ml.startswith("ollama:"):
        return _generate_ollama(prompt, m[7:])
    if ml.startswith(("gpt", "o1", "o3", "o4")):
        return _generate_openai(prompt, m)
    raise ValueError(f"Unknown LLM model: {m!r}")


def _generate_gemini(prompt: str, model: str) -> str:
    global _gemini_client
    from google import genai

    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        with _gemini_lock:
            if _gemini_client is None:
                _gemini_client = genai.Client(api_key=api_key)

    response = _gemini_client.models.generate_content(model=model, contents=[prompt])
    chunks: list[str] = []
    for part in getattr(response, "parts", None) or []:
        if getattr(part, "text", None):
            chunks.append(part.text)
    text = "".join(chunks).strip() or (getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Empty text response from Gemini")
    return text


def _generate_ollama(prompt: str, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=120)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("Empty text response from Ollama")
    return text


def _generate_openai(prompt: str, model: str) -> str:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("Empty text response from OpenAI")
    return text


def _generate_mistral(prompt: str, model: str) -> str:
    from openai import OpenAI

    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set")
    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("Empty text response from Mistral")
    return text


def generate_structured(
    prompt: str,
    response_model: Type[T],
    *,
    model: Optional[str] = None,
    backup_model: Optional[str] = None,
    hedge_after: float = 1.0,
    max_retries: int = 2,
) -> T:
    """Structured Pydantic output with optional backup model hedging."""
    primary = model or config.LLM_MODEL
    backup = backup_model or config.LLM_MODEL_BACKUP

    result_q: queue.Queue = queue.Queue()
    t_primary = threading.Thread(
        target=_structured_worker,
        args=(prompt, response_model, primary, max_retries, result_q),
        daemon=True,
    )
    t_primary.start()

    fast_err: Optional[Exception] = None
    try:
        status, _winner, value = result_q.get(timeout=hedge_after)
        if status == "ok":
            return value  # type: ignore[return-value]
        fast_err = value  # type: ignore[assignment]
    except queue.Empty:
        pass

    if not backup:
        if fast_err is not None:
            raise fast_err
        status, _winner, value = result_q.get(timeout=120)
        if status == "ok":
            return value  # type: ignore[return-value]
        raise value  # type: ignore[misc]

    threading.Thread(
        target=_structured_worker,
        args=(prompt, response_model, backup, max_retries, result_q),
        daemon=True,
    ).start()

    n_remaining = 1 if fast_err is not None else 2
    last_err: Exception = fast_err or RuntimeError("No LLM response (timeout)")
    for _ in range(n_remaining):
        try:
            status, _winner, value = result_q.get(timeout=120)
            if status == "ok":
                return value  # type: ignore[return-value]
            last_err = value  # type: ignore[assignment]
        except queue.Empty:
            break
    raise last_err


def _structured_worker(
    prompt: str,
    response_model: Type[T],
    model: str,
    max_retries: int,
    result_q: queue.Queue,
) -> None:
    try:
        result_q.put(("ok", model, _structured_call(prompt, response_model, model, max_retries)))
    except Exception as exc:
        result_q.put(("err", model, exc))


def _structured_call(
    prompt: str, response_model: Type[T], model: str, max_retries: int
) -> T:
    ml = model.lower()
    if ml.startswith("gemini"):
        return _structured_gemini(prompt, response_model, model, max_retries)
    if ml.startswith(("mistral", "open-mistral", "ministral", "codestral")):
        return _structured_mistral(prompt, response_model, model, max_retries)
    if ml.startswith(("gpt", "o1", "o3", "o4")):
        return _structured_openai(prompt, response_model, model)
    raise ValueError(f"generate_structured: unsupported model {model!r}")


def _structured_gemini(
    prompt: str, response_model: Type[T], model: str, max_retries: int
) -> T:
    global _gemini_client
    from google import genai
    from google.genai import types as genai_types

    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        with _gemini_lock:
            if _gemini_client is None:
                _gemini_client = genai.Client(api_key=api_key)

    current_prompt = prompt
    for attempt in range(max_retries + 1):
        response = _gemini_client.models.generate_content(
            model=model,
            contents=[current_prompt],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            text = "".join(
                p.text
                for p in (getattr(response, "parts", None) or [])
                if getattr(p, "text", None)
            ).strip()
        try:
            return response_model.model_validate_json(text)
        except (ValidationError, ValueError) as exc:
            if attempt == max_retries:
                raise
            current_prompt = (
                f"{prompt}\n\nVALIDATION ERROR (attempt {attempt + 1}): {exc}\n"
                "Fix and return valid JSON."
            )
    raise RuntimeError("Gemini structured call failed after retries")


def _structured_openai(prompt: str, response_model: Type[T], model: str) -> T:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    client = OpenAI(api_key=api_key)
    resp = client.beta.chat.completions.parse(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_model,
    )
    result = resp.choices[0].message.parsed
    if result is None:
        raise RuntimeError("Empty structured response from OpenAI")
    return result


def _structured_mistral(
    prompt: str, response_model: Type[T], model: str, max_retries: int
) -> T:
    from openai import OpenAI

    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set")
    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": prompt}]
    for attempt in range(max_retries + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            stream=False,
        )
        text = (resp.choices[0].message.content or "").strip()
        try:
            return response_model.model_validate_json(text)
        except (ValidationError, ValueError) as exc:
            if attempt == max_retries:
                raise
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": f"Validation error: {exc}. Return corrected JSON.",
                }
            )
    raise RuntimeError("Mistral structured call failed after retries")
