"""Cross-cutting infrastructure: configuration, prompt strings,
logging. Modules in here have no dependencies on `app.db`,
`app.agent`, or `app.api`, so they can be imported by any layer.
"""
