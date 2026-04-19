"""Pydantic schemas exposed over HTTP.

Distinct from the LLM-response schemas in ``app/agent/validators.py``;
those validate model output, these validate request/response bodies
and are referenced in the OpenAPI doc.

See DESIGN.md Section 6 for the API contract.
"""
