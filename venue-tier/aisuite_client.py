"""venue-tier/aisuite_client.py — Cloud AI 100 (AI Inference Suite) REST client.

OWNER: Gamma (Phase B4). Building now — don't touch.

Contract: endpoint/key/model from .env (AISUITE_*). OpenAI-compatible REST via
stdlib urllib (no new deps). advisory(zone_state) -> {en, hi, kn}. On timeout or
failure -> template_fallback (badged inference_backend:"template-local").
NEVER in the safety path.
"""
from __future__ import annotations


def advisory(zone_state: dict) -> dict:
    raise NotImplementedError("TODO(gamma B4): urllib POST -> {en,hi,kn} + fallback")
