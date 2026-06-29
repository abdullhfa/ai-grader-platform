"""Tests for PRO Android emulator automation."""
from pathlib import Path

from app.grading_mode_policy import deep_grading_flags, fast_grading_flags
from app.runtime_engines.android.project_probe import detect_project_stack, find_apk_artifact
from app.runtime_engines.android.mobile_automation import run_android_mobile_automation
from app.runtime_engines.registry import resolve_engine


def test_pro_only_android_emulator_flag():
    assert fast_grading_flags("fast")["enable_android_emulator_automation"] is False
    assert deep_grading_flags("deep")["enable_android_emulator_automation"] is True


def test_detect_flutter_project(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text("name: demo_app\n", encoding="utf-8")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
    probe = detect_project_stack(tmp_path)
    assert probe["flutter"] is True
    assert probe["platform_type"] == "flutter"


def test_detect_kotlin_android(tmp_path: Path):
    android = tmp_path / "android" / "app" / "src" / "main" / "java" / "com" / "demo"
    android.mkdir(parents=True)
    (android / "MainActivity.kt").write_text("class MainActivity {}\n", encoding="utf-8")
    (tmp_path / "android" / "app" / "build.gradle.kts").write_text(
        'plugins { id("com.android.application") }\n', encoding="utf-8"
    )
    probe = detect_project_stack(tmp_path)
    assert probe["kotlin"] is True
    assert probe["platform_type"] == "kotlin"


def test_android_engine_resolves_for_flutter(tmp_path: Path):
    (tmp_path / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
    engine = resolve_engine(tmp_path)
    assert engine is not None
    assert engine.engine_id == "android"


def test_mobile_automation_static_without_apk(tmp_path: Path):
    (tmp_path / "MainActivity.java").write_text("public class MainActivity {}\n", encoding="utf-8")
    result = run_android_mobile_automation(tmp_path, timeout_seconds=5)
    assert result["method"] == "static_only"
    assert result["error"] == "no_apk_for_emulator"


def test_find_apk_prefers_release(tmp_path: Path):
    out = tmp_path / "app" / "build" / "outputs" / "apk" / "release"
    out.mkdir(parents=True)
    (out / "app-debug.apk").write_bytes(b"PK\x03\x04" + b"\x00" * 40)
    (out / "app-release.apk").write_bytes(b"PK\x03\x04" + b"\x00" * 80)
    # minimal zip won't pass analyze but find should pick release by name
    found = find_apk_artifact(tmp_path)
    assert found is not None
    assert "release" in found.name.lower()
