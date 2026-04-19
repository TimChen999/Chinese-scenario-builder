"""LLM prompt templates as module-level string constants.

Keeping every prompt here -- not interpolated inline in the agent
modules -- makes it cheap to A/B test wording and easy to grep for
the actual instructions a future contributor wants to tune. The
prompts mirror DESIGN.md Section 7 ("Prompts") verbatim.

Three model tiers are referenced (see DESIGN.md Section 3):

* Gemini 2.5 Pro       -- vision OCR, scenario assembly
* Gemini 2.5 Flash     -- search-query generation, image quality filter
* Gemini 2.5 Flash Lite -- optional cheaper fallback
"""

from __future__ import annotations

# ─── OCR (vision) ──────────────────────────────────────────────────
# Gemini 2.5 Pro. Temperature 0.2 (deterministic). The system prompt
# locks the output to JSON shape; the user prompt is a one-liner that
# accompanies the image bytes.

OCR_SYSTEM = """\
You are looking at a real-world photo from China taken by a regular person.
Extract ALL visible Chinese text exactly as shown. Preserve:
- Original character forms (do NOT convert traditional <-> simplified)
- Original line breaks and spatial layout when meaningful (e.g., one
  menu item per line)
- Numbers and prices in the form they appear (元, ¥, RMB, plain digits)
- Any accompanying English / pinyin if present, in its original position

Do NOT:
- Translate
- Add pinyin
- Add interpretation
- Filter or "clean up" colloquialisms / regional terms / abbreviations

Output JSON:
{
  "raw_text": "<the extracted text, with newlines as \\n>",
  "confidence": <float 0-1, your self-assessment of OCR accuracy>,
  "scene_type": "menu" | "sign" | "notice" | "map" | "label" | "instruction" | "other",
  "notes": "<optional: anything unusual, e.g. handwritten, partly obscured>"
}
"""

OCR_USER = (
    "Extract every Chinese character visible in this image, exactly as shown, "
    "and return the JSON object described in your instructions."
)

# ─── Image quality filter ─────────────────────────────────────────
# Gemini 2.5 Flash. Temperature 0 (binary decision). Cheap + fast;
# the keep/reject verdict drives whether we pay for a Pro OCR call.

FILTER_SYSTEM = """\
You are filtering candidate images for a Chinese learning app. Look at
this image and decide if it should be kept.

Keep if ALL of:
- Real photo (not stock, not illustration, not screenshot of text editor)
- Contains visible Chinese text that a learner could read
- Text is legible (not blurred, not too small, not heavily obscured)
- Authentic context (a real menu, sign, label, etc., not a translation
  exercise, textbook page, or quiz)

Output JSON: {"keep": bool, "reason": "<one short sentence>"}
"""

FILTER_USER = (
    "Decide whether this image meets all of the criteria in your "
    "instructions. Return the JSON object described."
)

# ─── Scenario assembly ─────────────────────────────────────────────
# Gemini 2.5 Pro. Temperature 0.7 (some natural variety in scene_setup).
# The model NEVER edits raw_text -- the system prompt enforces this and
# assembly.py also passes raw_content through verbatim from the OCR
# result. Authenticity is the entire point (DESIGN.md Section 1).

ASSEMBLY_SYSTEM = """\
You are building a reading-comprehension scenario for a Mandarin Chinese
learner from a real-world image's extracted text.

Inputs:
- USER_REQUEST: what the learner asked for
- SCENE_TYPE: kind of source (menu, sign, etc.)
- RAW_TEXT: the verbatim extracted Chinese text -- DO NOT MODIFY THIS

Build:
1. scene_setup: ONE short paragraph (2-4 sentences) in natural Mandarin,
   second person, placing the learner in this scene. Example:
   "你刚走进一家老北京早餐店,坐下后服务员递给你菜单。你想点一份豆浆和油条..."
   - Use the raw text's vocabulary where possible
   - Don't add information not supported by the raw text

2. tasks: EXACTLY 3 comprehension tasks based ONLY on what's in raw_text.
   Each task must have a definite, verifiable answer derivable from the
   text alone. No interpretation tasks.
   - Mix task types: one "find" task, one "calculate/compare" task, one
     "comprehension" task
   - prompt: in ENGLISH (so the learner knows what to do without already
     understanding Chinese)
   - answer_type: "exact" (string match), "numeric" (number), or "multi"
     (multiple correct answers)
   - expected_answer: canonical correct answer
   - acceptable_answers: list of equivalent answers, e.g. ["油条",
     "youtiao", "Youtiao"] for transliteration tolerance. Always include
     the exact Chinese form.
   - explanation: 1-2 sentences in English explaining why, with reference
     to specific text from raw_text

Constraints:
- DO NOT alter raw_text in any way; it will be passed through verbatim
- DO NOT add pinyin, definitions, or translations of raw_text
- If raw_text doesn't support 3 verifiable tasks, output fewer; the
  validator will retry with a different image

Output JSON:
{
  "scene_setup": "...",
  "tasks": [
    {
      "prompt": "...",
      "answer_type": "exact|numeric|multi",
      "expected_answer": "...",
      "acceptable_answers": ["...", "..."],
      "explanation": "..."
    }
  ]
}
"""

ASSEMBLY_USER = """\
USER_REQUEST: {user_request}
SCENE_TYPE: {scene_type}
REGION: {region}
FORMAT_HINT: {format_hint}

RAW_TEXT:
{raw_text}
"""

# ─── Search-query generation (orchestrator stage 1) ────────────────
# Gemini 2.5 Flash. Cheap; 3 queries per call. The orchestrator uses
# these queries to drive parallel SerpAPI requests.

SEARCH_QUERIES_SYSTEM = """\
You help a learner of Mandarin Chinese find authentic real-world reading
material. Given a scenario prompt, output 3 Chinese-language Google Images
search queries that would surface real, in-the-wild photos of relevant
signs, menus, or notices.

Constraints:
- Each query must be in Simplified Chinese
- Each query must include the word 实拍 (real photo) or similar to bias
  toward user-uploaded photos rather than stock imagery
- Vary the queries: one specific, one general, one with regional flavor
  if the prompt names a region
- Output JSON: {"queries": ["q1", "q2", "q3"]}
"""

SEARCH_QUERIES_USER = """\
Scenario prompt: {prompt}
Scene hint: {scene_hint}
Region: {region}
"""

# ─── Query broadening (orchestrator retry) ────────────────────────
# Used when the filter stage returns fewer than MIN_KEEPERS usable
# images on the first attempt. We spend one more cheap Flash call to
# get broader queries before re-running search.

BROADEN_QUERIES_SYSTEM = """\
You are helping a Mandarin Chinese learner find authentic real-world
reading material. The previous round of search queries returned too
few usable images. Output 3 broader Chinese-language image search
queries that:
- Drop overly specific terms (regional dish names, brand names) where
  possible
- Use more common, generic vocabulary that still matches the scene
- Still bias toward user-uploaded photos (e.g. include 实拍 or 图片)
- Output JSON: {"queries": ["q1", "q2", "q3"]}
"""

BROADEN_QUERIES_USER = """\
Original prompt: {prompt}
Previous queries: {prev_queries}
Scene hint: {scene_hint}
Region: {region}
"""
