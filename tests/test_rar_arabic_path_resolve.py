"""RAR Arabic path corruption: unrar lb uses '?', rarfile keeps Unicode."""

from __future__ import annotations

from pathlib import PurePosixPath

from app.archive_extraction_utils import (
    _rar_member_ascii_fingerprint,
    _rar_path_looks_console_garbled,
    _rarfile_resolve_member_name,
)


class _FakeRar:
    def __init__(self, names: list[str]):
        self._names = names

    def namelist(self):
        return list(self._names)

    def getinfo(self, name: str):
        if name not in self._names and name.replace("\\", "/") not in {
            n.replace("\\", "/") for n in self._names
        }:
            raise KeyError(name)
        return name


def test_garbled_path_detection():
    assert _rar_path_looks_console_garbled(
        "Ahmad/??? (?+?)/P_03.exe"
    )
    assert not _rar_path_looks_console_garbled("Ahmad/folder/P_03.exe")


def test_ascii_fingerprint_matches_arabic_to_question_marks():
    unicode_path = "Ahmad Bakr/هدف (ب+ج)/P_03.exe"
    garbled_path = "Ahmad Bakr/??? (?+?)/P_03.exe"
    assert _rar_member_ascii_fingerprint(unicode_path) == _rar_member_ascii_fingerprint(
        garbled_path
    )


def test_resolve_garbled_lb_name_to_rarfile_unicode():
    unicode_name = "Ahmad Bakr Hatem/هدف (ب+ج)/docs/report.docx"
    garbled = "Ahmad Bakr Hatem/??? (?+?)/docs/report.docx"
    rf = _FakeRar(
        [
            unicode_name,
            "Ahmad Bakr Hatem/هدف (ب+ج)/game/main.gd",
            "other/readme.txt",
        ]
    )
    assert _rarfile_resolve_member_name(rf, unicode_name) == unicode_name
    assert _rarfile_resolve_member_name(rf, garbled) == unicode_name
    assert _rarfile_resolve_member_name(rf, "missing/file.docx") is None


def test_resolve_prefers_exact_basename_among_siblings():
    rf = _FakeRar(
        [
            "root/هدف/P_03.exe",
            "root/هدف/P_03.console.exe",
        ]
    )
    garbled = "root/???/P_03.exe"
    resolved = _rarfile_resolve_member_name(rf, garbled)
    assert resolved is not None
    assert PurePosixPath(resolved).name == "P_03.exe"
