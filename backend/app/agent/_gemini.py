"""Thin wrapper around the official ``google-genai`` async client.

Owns:

* The single shared :class:`google.genai.Client` instance (built lazily
  on first use, reused thereafter so connections pool).
* Translating SDK exceptions into a single :class:`GeminiError` so the
  rest of the agent layer never imports ``google.genai`` directly.
* Enforcing a per-call timeout via :func:`asyncio.wait_for`.
* The standard JSON-mode + ``response_schema`` calling convention
  documented in DESIGN.md Section 7 ("Gemini calling conventions").

Each agent module (vision, filter, assembly) calls
:func:`generate_text` and parses the returned JSON string with its
own Pydantic schema. We deliberately do NOT parse here so a single
``_gemini.generate_text`` can serve every model + schema combination.

Tests monkeypatch ``app.agent.<module>._gemini.generate_text`` to
inject canned responses without standing up a real client.
"""

from __future__ import annotations

import asyncio
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import Settings, get_settings

# ─── Model identifiers (DESIGN.md Section 7) ───────────────────────
MODEL_PRO = "gemini-2.5-pro"
MODEL_FLASH = "gemini-2.5-flash"
MODEL_FLASH_LITE = "gemini-2.5-flash-lite"


class GeminiError(Exception):
    """Single error type raised by this wrapper.

    Attributes
    ----------
    code:
        Machine-readable category (``"missing_api_key"``, ``"timeout"``,
        ``"api_error"``, ``"empty_response"``).
    message:
        Human-readable detail; safe to log.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_client: genai.Client | None = None


def get_client(settings: Settings | None = None) -> genai.Client:
    """Return the process-wide ``genai.Client``, building it on demand.

    Idempotent. Raises :class:`GeminiError` if ``GEMINI_API_KEY`` is
    missing -- we raise here, before any network call, so the user
    sees a configuration error immediately.
    """
    global _client
    if _client is None:
        if settings is None:
            settings = get_settings()
        if not settings.GEMINI_API_KEY:
            raise GeminiError("missing_api_key", "GEMINI_API_KEY is not configured")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def reset_client_for_tests() -> None:
    """Clear the cached client so tests can swap configurations."""
    global _client
    _client = None


def make_image_part(image_bytes: bytes, mime_type: str) -> types.Part:
    """Wrap raw image bytes into a :class:`google.genai.types.Part`.

    Centralised so all image-bearing calls construct the part the
    same way (and so unit tests can patch it if they want to inspect
    payloads).
    """
    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


async def generate_text(
    *,
    model: str,
    contents: list[Any],
    response_schema: Any | None = None,
    system_instruction: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
    timeout_s: float = 60.0,
    thinking_budget: int | None = None,
    client: genai.Client | None = None,
    settings: Settings | None = None,
) -> str:
    """Call ``generate_content`` and return the response text.

    Parameters
    ----------
    model
        One of :data:`MODEL_PRO` / :data:`MODEL_FLASH` /
        :data:`MODEL_FLASH_LITE`.
    contents
        The list of content parts (strings, :class:`types.Part`).
    response_schema
        Optional Pydantic model class. When set, the SDK forces the
        model into JSON mode and validates against the schema.
    system_instruction
        Optional system prompt; cleaner than prepending to ``contents``.
    temperature, max_output_tokens
        Standard generation knobs. Caller should pick per task type
        (DESIGN.md Section 7: 0.2 OCR, 0.7 assembly, 0 filter).
    timeout_s
        Per-call wall-clock cap enforced via :func:`asyncio.wait_for`.
    thinking_budget
        Per-call override for Gemini 2.5's "thinking" feature. ``0``
        disables thinking entirely (recommended for structured-output
        calls so the entire token budget produces parseable JSON);
        ``-1`` lets the model decide; a positive int caps thinking
        tokens. When ``None`` (default), thinking is auto-disabled if
        ``response_schema`` is supplied -- otherwise the SDK default
        applies.
    client, settings
        Test injection points. In production, both default to the
        shared cached values.

    Returns
    -------
    The ``response.text`` from Gemini (a JSON string when
    ``response_schema`` was supplied).

    Raises
    ------
    GeminiError
        Wraps every failure mode (timeout, API error, empty response)
        so callers never need to import the ``google.genai`` exception
        hierarchy.
    """
    if client is None:
        client = get_client(settings)

    config_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if response_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = response_schema
    if system_instruction is not None:
        config_kwargs["system_instruction"] = system_instruction

    # Gemini 2.5 enables internal "thinking" tokens by default, which
    # are billed against ``max_output_tokens``. For structured-output
    # calls (``response_schema`` set) we want every token spent on the
    # JSON we actually parse, so we disable thinking unless the caller
    # explicitly asked for it. Without this guard, low-budget calls
    # like the filter (256 tokens) get truncated mid-preamble and the
    # parse downstream raises ``JSONDecodeError``.
    effective_thinking_budget = thinking_budget
    if effective_thinking_budget is None and response_schema is not None:
        effective_thinking_budget = 0
    if effective_thinking_budget is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=effective_thinking_budget
        )

    config = types.GenerateContentConfig(**config_kwargs)

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=timeout_s,
        )
    except TimeoutError as exc:  # asyncio.TimeoutError is an alias on 3.11+
        raise GeminiError("timeout", f"Gemini call exceeded {timeout_s}s") from exc
    except genai_errors.APIError as exc:
        raise GeminiError("api_error", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 -- defensive: any SDK error becomes our error
        raise GeminiError("api_error", f"Unexpected Gemini failure: {exc}") from exc

    text = getattr(response, "text", None)
    if not text:
        raise GeminiError("empty_response", "Gemini returned no text content")
    return text
