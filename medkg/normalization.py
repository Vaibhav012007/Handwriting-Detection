"""Non-clinical catalog normalization helpers."""
import re
import unicodedata

_FORMS = {
    "tab": "tablet", "tablet": "tablet", "cap": "capsule", "capsule": "capsule",
    "syrup": "syrup", "susp": "suspension", "suspension": "suspension",
    "inj": "injection", "injection": "injection", "cream": "cream",
    "ointment": "ointment", "drops": "drops",
}

def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()

def normalize_unit(value: str | None) -> str | None:
    if not value:
        return None
    units = {"mg": "mg", "g": "g", "mcg": "mcg", "µg": "mcg", "ml": "mL", "iu": "IU"}
    return units.get(value.strip().casefold(), value.strip())

def normalize_dosage_form(value: str | None) -> str | None:
    if not value:
        return None
    return _FORMS.get(normalize_text(value), normalize_text(value))
