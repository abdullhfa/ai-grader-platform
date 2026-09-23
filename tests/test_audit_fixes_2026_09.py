"""Regression tests for the September 2026 audit fixes."""
from __future__ import annotations

from unittest.mock import patch

from app import textbook_analyzer as ta


def _ai(details):
    return {"topic": "t", "required_criteria": list(details), "criteria_details": details}


def test_criterion_key_normalises_formats():
    assert ta._criterion_key("8/B.P4") == ("B", "P4")
    assert ta._criterion_key("b-m2") == ("B", "M2")
    assert ta._criterion_key("P1") == ("", "P1")
    assert ta._criterion_key("nonsense") == ("", "")


def test_invented_criterion_is_dropped_and_reported():
    res = ta._drop_unverified_criteria(
        _ai({"A.P1": {"name": "x"}, "A.D1": {"name": "invented"}}), ["A.P1"]
    )
    assert list(res["criteria_details"]) == ["A.P1"]
    assert res["required_criteria"] == ["A.P1"]
    assert res["rejected_criteria"] == ["A.D1"]


def test_wrong_learning_aim_is_dropped():
    res = ta._drop_unverified_criteria(_ai({"C.P1": {}}), ["A.P1"])
    assert res["criteria_details"] == {}


def test_code_without_aim_in_brief_matches_any_aim():
    res = ta._drop_unverified_criteria(_ai({"A.P1": {}}), ["P1"])
    assert list(res["criteria_details"]) == ["A.P1"]


def test_official_unit_list_counts_as_source():
    res = ta._drop_unverified_criteria(
        _ai({"B.M2": {}}), [], [{"criteria_level": "8/B.M2"}]
    )
    assert list(res["criteria_details"]) == ["B.M2"]


def test_nothing_to_verify_against_keeps_but_flags():
    res = ta._drop_unverified_criteria(_ai({"A.P1": {}}), [], None)
    assert list(res["criteria_details"]) == ["A.P1"]
    assert res["unverified_criteria"] == ["A.P1"]


def test_all_invented_falls_back_to_regex():
    with patch.object(ta, "_call_ai_json", return_value=_ai({"Z.D9": {}})), \
         patch.object(ta, "analyze_assignment_requirements_regex", return_value={"fallback": True}) as fb:
        out = ta.analyze_assignment_requirements("To achieve A.P1 you must build a form.")
    assert out == {"fallback": True}
    fb.assert_called_once()


def test_settings_secret_masking():
    import main
    assert main._mask_secret("") == ""
    masked = main._mask_secret("AIzaREALKEY_abcd9999")
    assert masked.endswith("9999") and "REALKEY" not in masked
    assert main._is_masked_secret(masked)
    assert not main._is_masked_secret("AIzaREALKEY_abcd9999")
    # Short keys reveal nothing at all
    assert main._mask_secret("abc") == main._SECRET_MASK_PREFIX


def test_settings_and_governance_apis_require_login():
    from fastapi.testclient import TestClient
    import main
    c = TestClient(main.app)
    assert c.get("/api/get-settings").status_code == 401
    assert c.post("/api/save-settings", json={"ollama_base_url": "http://x"}).status_code == 401
    assert c.post("/api/test-provider", json={"provider": "ollama"}).status_code == 401
    assert c.get("/api/governance/artifact/abc").status_code == 401
    assert c.get("/api/governance-pilot/epistemic-evidence/batch/1").status_code == 401
