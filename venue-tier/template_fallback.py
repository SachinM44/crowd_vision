"""venue-tier/template_fallback.py — offline trilingual advisory fallback.

OWNER: Gamma. Used automatically when the cloud is slow/unreachable/unconfigured
(Hard Rule 2: badged inference_backend:"template-local"). Dead-simple and always
works — templates embedded in code, no external dependency. The Sarvam upgrade
(if adopted at G2) re-badges these "sarvam-edge" via sarvam_adapter.

Off the safety path — advisories inform; they never gate.
"""
from __future__ import annotations

# EN/HI/KN templates keyed by risk. {zone} and {exit} are filled per call.
_TEMPLATES = {
    "RED": {
        "en": "Zone {zone} is dangerously crowded. Do not enter. Please move toward the {exit} exits.",
        "hi": "ज़ोन {zone} में ख़तरनाक भीड़ है। अंदर न आएं। कृपया {exit} द्वार की ओर बढ़ें।",
        "kn": "ವಲಯ {zone} ಅಪಾಯಕಾರಿಯಾಗಿ ಜನದಟ್ಟಣೆಯಿಂದ ಕೂಡಿದೆ. ಒಳಗೆ ಬರಬೇಡಿ. ದಯವಿಟ್ಟು {exit} ನಿರ್ಗಮನದ ಕಡೆಗೆ ಸಾಗಿ.",
    },
    "AMBER": {
        "en": "Zone {zone} is filling up. Please use the {exit} exits to keep moving.",
        "hi": "ज़ोन {zone} भर रहा है। चलते रहने के लिए कृपया {exit} द्वार का उपयोग करें।",
        "kn": "ವಲಯ {zone} ತುಂಬುತ್ತಿದೆ. ಚಲಿಸುತ್ತಿರಲು ದಯವಿಟ್ಟು {exit} ನಿರ್ಗಮನ ಬಳಸಿ.",
    },
    "GREEN": {
        "en": "Zone {zone} is clear. Normal flow.",
        "hi": "ज़ोन {zone} साफ़ है। सामान्य आवाजाही।",
        "kn": "ವಲಯ {zone} ಸ್ಪಷ್ಟವಾಗಿದೆ. ಸಾಮಾನ್ಯ ಸಂಚಾರ.",
    },
}
_EXIT = {"A": "north", "B": "north", "C": "east", "D": "east"}


def advisory(context: dict) -> dict:
    """Build a venue.advisory payload (no envelope) from a zone context.

    context: {"zone_id", "risk", "density_per_m2"(opt), "scope"(opt), "seq"(opt)}
    """
    zone = context.get("zone_id", "?")
    risk = context.get("risk", "AMBER")
    tpl = _TEMPLATES.get(risk, _TEMPLATES["AMBER"])
    ex = _EXIT.get(zone, "nearest")
    seq = context.get("seq", 0)
    return {
        "advisory_id": f"adv-tmpl-{seq}",
        "scope": context.get("scope", f"zone:{zone}"),
        "en": tpl["en"].format(zone=zone, exit=ex),
        "hi": tpl["hi"].format(zone=zone, exit=ex),
        "kn": tpl["kn"].format(zone=zone, exit=ex),
        "model_id": "template-v1",
        "inference_backend": "template-local",
        "latency_ms": 0.0,
    }
