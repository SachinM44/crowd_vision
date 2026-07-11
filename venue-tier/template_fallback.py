"""venue-tier/template_fallback.py — offline trilingual advisory fallback.

OWNER: Gamma (Phase B4). Building now — don't touch.

Used automatically when the cloud is slow/unreachable (Hard Rule 2: badged
inference_backend:"template-local"). Sarvam upgrade (if offered at 11:30) slots
in via sarvam_adapter and re-badges "sarvam-edge". Templates in prompts/.
"""
from __future__ import annotations


def advisory(zone_state: dict) -> dict:
    raise NotImplementedError("TODO(gamma B4): fill EN/HI/KN templates -> template-local")
