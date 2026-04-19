"""Unit tests for ``app.agent._gemini``.

These tests stand up a fake ``client.aio.models.generate_content``
that captures the ``config`` it was called with, so we can assert
on the resulting ``GenerateContentConfig`` (specifically the
``thinking_config`` field, which our wrapper sets automatically when
a ``response_schema`` is supplied).

We deliberately do NOT hit the network. The whole point of routing
every call through ``_gemini.generate_text`` is that this single
choke point is mockable.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from app.agent import _gemini


class _DummySchema(BaseModel):
    """Trivial response schema; the SDK only inspects its presence."""

    ok: bool


class _CapturingClient:
    """Minimal fake of ``genai.Client`` recording the last config used.

    Mirrors the surface ``_gemini.generate_text`` actually touches:
    ``client.aio.models.generate_content(model=, contents=, config=)``.
    """

    def __init__(self, response_text: str = '{"ok": true}') -> None:
        self.response_text = response_text
        self.last_config: Any = None
        self.last_model: str | None = None
        self.last_contents: Any = None

        client = self

        class _Models:
            async def generate_content(
                self, *, model: str, contents: Any, config: Any
            ) -> Any:
                client.last_model = model
                client.last_contents = contents
                client.last_config = config
                return SimpleNamespace(text=client.response_text)

        self.aio = SimpleNamespace(models=_Models())


@pytest.mark.asyncio
async def test_thinking_disabled_by_default_when_response_schema_set() -> None:
    """A Flash call with ``response_schema`` auto-disables thinking.

    This is the regression test for the filter-truncation bug:
    Gemini 2.5 Flash burns the (tiny) token budget on internal
    thinking and emits no JSON. We want ``thinking_budget=0`` to be
    set automatically so the entire budget goes to output.
    """
    client = _CapturingClient()

    text = await _gemini.generate_text(
        model=_gemini.MODEL_FLASH,
        contents=["hi"],
        response_schema=_DummySchema,
        client=client,
    )

    assert text == '{"ok": true}'
    assert client.last_config is not None
    assert client.last_config.thinking_config is not None
    assert client.last_config.thinking_config.thinking_budget == 0


@pytest.mark.asyncio
async def test_thinking_left_alone_for_pro_with_response_schema() -> None:
    """Pro must NOT have thinking auto-disabled.

    Regression test: gemini-2.5-pro rejects ``thinking_budget=0`` with
    ``INVALID_ARGUMENT: This model only works in thinking mode.`` The
    earlier auto-disable was unconditional and broke every Pro call
    that used a response_schema (i.e. every OCR + assembly call).
    Auto-disable must be Flash-only.
    """
    client = _CapturingClient()

    await _gemini.generate_text(
        model=_gemini.MODEL_PRO,
        contents=["hi"],
        response_schema=_DummySchema,
        client=client,
    )

    assert client.last_config.thinking_config is None


@pytest.mark.asyncio
async def test_thinking_disabled_for_flash_lite_with_response_schema() -> None:
    """Flash-Lite is also a Flash variant and gets the auto-disable."""
    client = _CapturingClient()

    await _gemini.generate_text(
        model=_gemini.MODEL_FLASH_LITE,
        contents=["hi"],
        response_schema=_DummySchema,
        client=client,
    )

    assert client.last_config.thinking_config is not None
    assert client.last_config.thinking_config.thinking_budget == 0


@pytest.mark.asyncio
async def test_thinking_left_alone_without_response_schema() -> None:
    """Calls without ``response_schema`` keep the SDK default thinking.

    Plain text generation can legitimately benefit from thinking, and
    we should not silently change behavior for callers that did not
    ask for structured output.
    """
    client = _CapturingClient(response_text="hello")

    await _gemini.generate_text(
        model=_gemini.MODEL_FLASH,
        contents=["hi"],
        client=client,
    )

    assert client.last_config.thinking_config is None


@pytest.mark.asyncio
async def test_thinking_budget_explicit_override_wins() -> None:
    """Explicit ``thinking_budget`` overrides the auto-disable.

    Lets a future caller opt back into thinking + structured output if
    they need it, without losing the safe default.
    """
    client = _CapturingClient()

    await _gemini.generate_text(
        model=_gemini.MODEL_FLASH,
        contents=["hi"],
        response_schema=_DummySchema,
        thinking_budget=1024,
        client=client,
    )

    assert client.last_config.thinking_config.thinking_budget == 1024


@pytest.mark.asyncio
async def test_response_schema_sets_json_mime_type() -> None:
    """Sanity check: structured output is forced to JSON MIME."""
    client = _CapturingClient()

    await _gemini.generate_text(
        model=_gemini.MODEL_FLASH,
        contents=["hi"],
        response_schema=_DummySchema,
        client=client,
    )

    assert client.last_config.response_mime_type == "application/json"
    assert client.last_config.response_schema is _DummySchema
