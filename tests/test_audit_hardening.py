"""Tests for audit-driven security helpers."""
from app.graders.rule_marker import RuleBasedMarker
from app.security.password_policy import validate_password


def test_password_policy_requires_complexity():
    ok, errors = validate_password("short")
    assert ok is False
    assert errors

    ok, _ = validate_password("GoodPass1")
    assert ok is True


def test_rule_marker_unit8_domain_keywords():
    text = (
        "This game uses Unity with player movement, collision detection, "
        "score system, and gameplay levels exported for playtest."
    )
    result = RuleBasedMarker.evaluate_criterion(
        text=text,
        criteria_level="8/C.P1",
        criteria_description="Describe game features",
    )
    assert result["evidence"]["domain_count"] >= 3
