"""Agent layer: search -> filter -> OCR -> assemble pipeline.

Each module under here exposes one async function plus its custom
exception type. Modules avoid touching the database directly; the
orchestrator (added in Step 6) wires them together and the API layer
(Step 7) persists the result. See DESIGN.md Section 7 (Agent Flow).
"""
