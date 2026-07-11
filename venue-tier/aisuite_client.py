"""venue-tier/aisuite_client.py — Cloud AI 100 (AI Inference Suite) REST client.

OWNER: Gamma. Requests a trilingual advisory from the Cloud AI 100 endpoint
(OpenAI-compatible /chat/completions) using stdlib urllib (no extra deps).
Endpoint/key/model come from .env (AISUITE_*). On ANY failure — missing creds,
timeout, bad response — it falls back to template_fallback, badged honestly
(inference_backend:"template-local" vs "cloud-ai100"). NEVER in the safety path.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))       # sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # crowdvision._lib

import template_fallback  # noqa: E402

_SYS_PROMPT = (
    "You are a venue safety advisor. Given a zone's crowd state, produce a short "
    "public-address advisory in English, Hindi, and Kannada. Reply ONLY as JSON "
    '{"en":...,"hi":...,"kn":...}. Be calm, direct, name which exits to use.'
)


def _cloud_advisory(context: dict, endpoint: str, key: str, model: str,
                    timeout: float = 3.0) -> dict:
    body = {
        "model": model or "default",
        "messages": [
            {"role": "system", "content": _SYS_PROMPT},
            {"role": "user", "content": json.dumps(context)},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    latency = round((time.monotonic() - t0) * 1000, 1)
    content = data["choices"][0]["message"]["content"]
    langs = json.loads(content)  # model returns {en,hi,kn}
    return {
        "advisory_id": f"adv-cloud-{context.get('seq', 0)}",
        "scope": context.get("scope", f"zone:{context.get('zone_id', '?')}"),
        "en": langs.get("en", ""), "hi": langs.get("hi", ""), "kn": langs.get("kn", ""),
        "model_id": model or "cloud-ai100-advisor",
        "inference_backend": "cloud-ai100", "latency_ms": latency,
    }


def advisory(context: dict) -> dict:
    """Trilingual advisory via Cloud AI 100, or template-local on any failure."""
    endpoint = os.environ.get("AISUITE_ENDPOINT", "").strip()
    key = os.environ.get("AISUITE_KEY", "").strip()
    model = os.environ.get("AISUITE_MODEL", "").strip()
    if not endpoint or not key:
        return template_fallback.advisory(context)     # not configured -> template
    try:
        return _cloud_advisory(context, endpoint, key, model)
    except Exception:  # noqa: BLE001 — cloud dead => zones don't care (uplink-cut)
        return template_fallback.advisory(context)
