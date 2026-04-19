"""Cross-cutting services that touch the outside world: image store,
job runner. Imported by the API layer; the agent layer stays free of
filesystem + persistence concerns.
"""
