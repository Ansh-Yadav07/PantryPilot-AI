from datetime import datetime, timedelta

from app.services.ingredient_catalog import CATALOG, normalize_ingredient_name
from app.services.inventory_service import (compute_expiry_display, compute_expiry_status, convert_from_base,
                                            convert_to_base, days_until, normalize_unit, parse_quantity_string,
                                            units_compatible)
from app.services.waste_prediction import WastePredictionService
from app.services.gemini_client import _extract_text, _strip_fences, GeminiError
from app.utils.uploads import sniff_image_type

import pytest


def test_catalog_has_22_classes_matching_model_order():
    from app.services.detection_service import CLASS_NAMES
    assert len(CATALOG) == 22
    assert [k for k, _ in sorted(CATALOG.items(), key=lambda kv: kv[1]["class_index"])] == CLASS_NAMES


@pytest.mark.parametrize("raw,expected", [("Tomatoes", "tomato"), ("green beans", "green_beans"),
                                           ("Bell Pepper", "capsicum"), ("chocolate", None)])
def test_normalization(raw, expected):
    assert normalize_ingredient_name(raw) == expected


def test_units():
    assert normalize_unit("Kilograms") == "kg"
    assert units_compatible("g", "kg") and not units_compatible("g", "pcs")
    assert convert_to_base(1.5, "kg") == (1500.0, "weight")
    assert convert_from_base(750, "weight") == (750, "g")
    assert parse_quantity_string("500 g") == (500.0, "g")
    assert parse_quantity_string("lots") == (None, "pcs")


def test_expiry_uses_calendar_days():
    now = datetime.utcnow()
    tonight = now.replace(hour=23, minute=59)
    assert compute_expiry_display(tonight) == "Expires today"
    tomorrow_early = (now + timedelta(days=1)).replace(hour=0, minute=1)
    assert compute_expiry_display(tomorrow_early) == "Expires tomorrow"
    assert compute_expiry_status((now - timedelta(days=1))) == "expired"
    assert compute_expiry_status(now + timedelta(days=3)) == "expiring_soon"
    assert compute_expiry_status(now + timedelta(days=6)) == "use_soon"
    assert compute_expiry_status(now + timedelta(days=30)) == "fresh"
    assert compute_expiry_status(None) == "unknown"
    assert days_until(datetime(2026, 1, 2, 0, 5), now=datetime(2026, 1, 1, 23, 55)) == 1


def test_waste_rules():
    now = datetime(2026, 1, 10, 12)
    assert WastePredictionService.predict_waste_risk("x", datetime(2026, 1, 9), 1, now=now)["riskLevel"] == "CRITICAL"
    assert WastePredictionService.predict_waste_risk("x", datetime(2026, 1, 12), 1, now=now)["riskLevel"] == "HIGH"
    assert WastePredictionService.predict_waste_risk("x", datetime(2026, 1, 30), 1, now=now)["riskLevel"] == "LOW"


def test_gemini_response_parsing():
    body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "thinking...", "thought": True}, {"text": '```json\n[1, 2]\n```'}]}}]}
    assert _strip_fences(_extract_text(body)) == "[1, 2]"
    with pytest.raises(GeminiError):
        _extract_text({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(GeminiError):
        _extract_text({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})


def test_image_sniffing():
    assert sniff_image_type(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert sniff_image_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_type(b"%PDF-1.4") == ""
