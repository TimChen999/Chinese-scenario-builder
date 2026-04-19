"""Live end-to-end orchestration test.

Runs the full agent pipeline against the real Gemini + DuckDuckGo
endpoints. Gated by ``RUN_LIVE_TESTS=1``; off by default.

Three prompts (per DESIGN.md Step 6 DoD) cover different scene
families: menu, navigation/sign, restaurant/ambient. Each run is
expected to take 30-90 s and cost a small amount in Gemini tokens.

Output is printed for manual review -- live tests are alerts, not
regressions, so seeing the real ScenarioDraft is the point.
"""

from __future__ import annotations

import os
from dataclasses import asdict

import pytest

from app.agent.orchestrator import run_generation

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LIVE_TESTS"),
    reason="Set RUN_LIVE_TESTS=1 to opt into live external-service tests.",
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt, region",
    [
        ("ordering breakfast in a Beijing 早餐店", "Beijing"),
        ("navigating a Shanghai metro station", "Shanghai"),
        ("eating hotpot in Chongqing", "Chongqing"),
    ],
)
async def test_full_real_run(prompt: str, region: str) -> None:
    """One end-to-end orchestration call per prompt; assert sanity invariants."""
    progress: list[tuple[str, dict]] = []

    async def on_progress(stage: str, detail: dict) -> None:
        progress.append((stage, detail))

    draft = await run_generation(prompt, region=region, on_progress=on_progress)

    print(f"\n=== {prompt} ===")
    for stage, detail in progress:
        print(f"  - {stage}: {detail}")
    print(f"scene_type: {draft.scene_type}")
    print(f"scene_setup: {draft.scene_setup}")
    print(f"raw_content:\n{draft.raw_content}")
    for t in draft.tasks:
        print(f"  task: {asdict(t)}")

    assert draft.raw_content, "raw_content must not be empty"
    assert 1 <= len(draft.tasks) <= 5, "tasks count out of bounds"
    assert any(stage == "done" for stage, _ in progress), "done event missing"
