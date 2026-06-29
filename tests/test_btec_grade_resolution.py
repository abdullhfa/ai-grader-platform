"""Tests for BTEC grade SSOT (app.btec_grade_resolution)."""
from app.btec_grade_resolution import determine_grade_level, parse_btec_grade_short


def _crit(level: str, achieved: bool) -> dict:
    return {"criteria_level": level, "achieved": achieved, "score": 100 if achieved else 0}


def test_determine_grade_level_u_when_pass_incomplete():
    crit = [_crit("A.P1", True), _crit("A.P2", False), _crit("A.M1", True)]
    assert determine_grade_level(crit) == "U"


def test_determine_grade_level_p_all_pass():
    crit = [_crit("A.P1", True), _crit("A.P2", True), _crit("A.M1", False)]
    assert determine_grade_level(crit) == "P"


def test_determine_grade_level_m():
    crit = [_crit("A.P1", True), _crit("A.P2", True), _crit("A.M1", True), _crit("A.D1", False)]
    assert determine_grade_level(crit) == "M"


def test_parse_btec_grade_short():
    assert parse_btec_grade_short("Distinction (D)") == "D"
    assert parse_btec_grade_short("M") == "M"
    assert parse_btec_grade_short("") == "U"
