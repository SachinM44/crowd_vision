"""crowdvision._lib — small, Gamma-owned shared helpers.

These implement the docs/MESSAGES.md contract (envelope, topics, honest
backend badges) so every lane stays schema-consistent. Coding to the schema is
Hard Rule 1 — this is NOT a lane-internal coupling. Any lane may emit raw JSON
instead; both conform as long as the envelope matches MESSAGES.md.
"""

from . import messages, config, mqttc  # noqa: F401
