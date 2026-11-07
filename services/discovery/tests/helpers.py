"""Shared paths and builders for the Discovery template tests. Fictional data only."""
import json
from pathlib import Path

DISCOVERY = Path(__file__).resolve().parents[1]
REPO = DISCOVERY.parents[1]
TEMPLATE_DIR = DISCOVERY / "templates" / "trading-distribution"
TEMPLATE = TEMPLATE_DIR / "blueprint.template.json"
QUESTIONS = TEMPLATE_DIR / "questions.json"
QUESTIONS_SCHEMA = TEMPLATE_DIR / "questions.schema.json"
BLUEPRINT_SCHEMA = REPO / "contracts" / "blueprint.schema.json"
REGISTRY_DIR = REPO / "services" / "blueprint" / "fixtures" / "registry"

ANSWERS = {
    "sa": {"country": "sa", "name_ar": "شركة اختبار للتجارة", "name_en": "Sample Trading Co.",
           "branches": 2, "vat_registered": True, "vat_number": "300000000000003", "languages": ["ar", "en"]},
    "ae": {"country": "ae", "name_ar": "شركة اختبار للتجارة", "name_en": "Sample Trading LLC",
           "branches": 1, "vat_registered": True, "vat_number": "100000000000003", "currency": "AED"},
    "eg": {"country": "eg", "name_ar": "شركة اختبار للتجارة", "name_en": "Sample Trading SAE",
           "branches": 3, "vat_registered": False, "currency": "EGP"},
}


def registry():
    reg = {}
    for f in sorted(REGISTRY_DIR.glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        reg.setdefault(m["id"], []).append(m)
    return reg
