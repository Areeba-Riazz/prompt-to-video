"""
Centralised LLM client — shared/utils/llm_client.py

Single-turn chat completions via Groq (OpenAI-compatible) or Google Gemini.
Primary provider is chosen via LLM_PROVIDER; if it fails for any reason
(quota, network, key error, …) the other provider is automatically tried
as a fallback before giving up.

Configuration (read directly from environment / .env):
    LLM_PROVIDER   — "groq" (default) or "gemini"
    LLM_MODEL      — optional model override; defaults per-provider below
    GROQ_API_KEY   — required when LLM_PROVIDER=groq (also used as fallback)
    GEMINI_API_KEY — required when LLM_PROVIDER=gemini (also used as fallback)
    GEMINI_API_KEY2 — secondary Gemini key tried before falling back to Groq

Public API:
    chat_json(*, system, user, temperature) -> dict[str, Any]
    chat_text(*, system, user, temperature) -> str
"""

from __future__ import annotations

import json
import logging
import os
import warnings
from typing import Any

# Suppress the google-generativeai end-of-life FutureWarning — it's noise.
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

logger = logging.getLogger("LLMClient")

# ── Provider defaults ──────────────────────────────────────────────────────────

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_DEFAULT_MODEL_GROQ = "llama-3.3-70b-versatile"
_DEFAULT_MODEL_GEMINI = "gemini-2.0-flash"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _provider() -> str:
    """Return normalised provider name; defaults to 'groq'."""
    return (os.environ.get("LLM_PROVIDER") or "groq").strip().lower()


def _model_for(provider: str) -> str:
    """
    Return the model name for the given provider.
    An explicit LLM_MODEL env var always wins.
    """
    explicit = (os.environ.get("LLM_MODEL") or "").strip()
    if explicit:
        return explicit
    return _DEFAULT_MODEL_GEMINI if provider == "gemini" else _DEFAULT_MODEL_GROQ


def _groq_client():
    """Create and return an OpenAI client pointed at the Groq endpoint."""
    from openai import OpenAI  # pip install openai

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def _gemini_model(system: str):
    """Configure google-generativeai and return a GenerativeModel instance."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as genai  # pip install google-generativeai

    # Try primary key, then GEMINI_API_KEY2 as a secondary within Gemini.
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY2", "").strip()
    )
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        _model_for("gemini"),
        system_instruction=system,
    )


# ── Groq implementations ───────────────────────────────────────────────────────

def _chat_groq_json(system: str, user: str, temperature: float) -> dict[str, Any]:
    client = _groq_client()
    response = client.chat.completions.create(
        model=_model_for("groq"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    if not raw:
        raise RuntimeError("Groq returned empty content.")
    return json.loads(raw)


def _chat_groq_text(system: str, user: str, temperature: float) -> str:
    client = _groq_client()
    response = client.chat.completions.create(
        model=_model_for("groq"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    raw = response.choices[0].message.content
    if not raw:
        raise RuntimeError("Groq returned empty content.")
    return raw.strip()


# ── Gemini implementations ─────────────────────────────────────────────────────

def _chat_gemini_json(system: str, user: str, temperature: float) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as genai

    model = _gemini_model(system)
    response = model.generate_content(
        user,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    raw = response.text
    if not raw:
        raise RuntimeError("Gemini returned empty content.")
    return json.loads(raw)


def _chat_gemini_text(system: str, user: str, temperature: float) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        import google.generativeai as genai

    model = _gemini_model(system)
    response = model.generate_content(
        user,
        generation_config=genai.GenerationConfig(temperature=temperature),
    )
    raw = response.text
    if not raw:
        raise RuntimeError("Gemini returned empty content.")
    return raw.strip()


# ── Fallback routing ───────────────────────────────────────────────────────────

def _fallback_provider(primary: str) -> str | None:
    """
    Return the other provider if its key is available, else None.
    gemini -> groq  (if GROQ_API_KEY is set)
    groq   -> gemini (if GEMINI_API_KEY or GEMINI_API_KEY2 is set)
    """
    if primary == "gemini" and os.environ.get("GROQ_API_KEY", "").strip():
        return "groq"
    if primary == "groq" and (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY2", "").strip()
    ):
        return "gemini"
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def chat_json(*, system: str, user: str, temperature: float = 0.7) -> dict[str, Any]:
    """
    Single-turn chat that must return a JSON object (parsed to dict).

    Tries the primary LLM_PROVIDER first. On any failure, automatically
    retries with the other provider (if its key exists). Raises only if
    both providers fail.
    """
    primary = _provider()
    _impls: dict[str, Any] = {"groq": _chat_groq_json, "gemini": _chat_gemini_json}

    if primary not in _impls:
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER={primary!r}. Set it to 'groq' or 'gemini' in .env."
        )

    try:
        return _impls[primary](system, user, temperature)
    except Exception:
        fallback = _fallback_provider(primary)
        if fallback is None:
            raise  # no fallback key available — propagate original error
        logger.warning(
            "⚠️ [LLMClient] %s failed — now trying %s.",
            primary.capitalize(), fallback.capitalize(),
        )

    # Fallback attempt — propagates naturally if this also fails.
    return _impls[fallback](system, user, temperature)


def chat_text(*, system: str, user: str, temperature: float = 0.7) -> str:
    """
    Single-turn chat returning plain text.

    Tries the primary LLM_PROVIDER first, falls back to the other provider
    automatically if the primary fails.
    """
    primary = _provider()
    _impls: dict[str, Any] = {"groq": _chat_groq_text, "gemini": _chat_gemini_text}

    if primary not in _impls:
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER={primary!r}. Set it to 'groq' or 'gemini' in .env."
        )

    try:
        return _impls[primary](system, user, temperature)
    except Exception:
        fallback = _fallback_provider(primary)
        if fallback is None:
            raise
        logger.warning(
            "⚠️ [LLMClient] %s failed — now trying %s.",
            primary.capitalize(), fallback.capitalize(),
        )

    return _impls[fallback](system, user, temperature)
