"""Plain dataclasses passed between agent stages.

These are the shapes that travel through the pipeline; they are NOT
ORM objects. The orchestrator hands a :class:`ScenarioDraft` to the
API layer, which translates it into Scenario / Task rows.

Field names mirror DESIGN.md Section 7 (Module contracts) verbatim
so the design doc and the code stay in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageResult:
    """One candidate image from an image-search backend.

    ``url`` is the direct image URL we will download. ``source_page_url``
    points to the page the image lives on (where applicable). The
    ``width`` / ``height`` fields are advisory; some search providers
    omit them.
    """

    url: str
    title: str | None = None
    source_page_url: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class DownloadedImage:
    """An :class:`ImageResult` after we fetched the bytes.

    ``mime`` is the response Content-Type (e.g. ``image/jpeg``);
    callers should not trust the URL extension alone.
    """

    bytes_: bytes
    mime: str
    original: ImageResult


@dataclass
class FilterVerdict:
    """A keep / reject decision for a candidate image.

    ``reason`` is a short LLM-supplied sentence; surfaced in logs and
    SSE progress events so the user can see why a candidate dropped.
    """

    image: DownloadedImage
    keep: bool
    reason: str


@dataclass
class OcrResult:
    """Raw text extracted from an image plus self-reported confidence.

    The ``raw_text`` field holds the OCR output verbatim and is the
    sole source of truth for what the user reads in the scenario --
    no downstream code is permitted to alter it (DESIGN.md Section 1
    "authenticity" + Section 5 ``raw_content``).
    """

    image: DownloadedImage
    raw_text: str
    confidence: float
    scene_type_guess: str
    notes: str | None = None


@dataclass
class TaskDraft:
    """A pre-persistence task spec produced by the assembly stage."""

    prompt: str
    answer_type: str  # exact | numeric | multi
    expected_answer: str
    acceptable_answers: list[str] = field(default_factory=list)
    explanation: str | None = None


@dataclass
class ScenarioDraft:
    """A pre-persistence scenario spec produced by the assembly stage.

    The orchestrator returns one of these; the API layer turns it
    into Scenario + Task DB rows and a saved image file.
    """

    scene_type: str
    scene_setup: str
    raw_content: str
    tasks: list[TaskDraft]
    source_image: DownloadedImage
