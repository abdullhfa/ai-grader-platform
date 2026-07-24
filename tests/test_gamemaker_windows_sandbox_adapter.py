from pathlib import Path

from app.runtime_engines.gamemaker.windows_sandbox_adapter import WindowsSandboxGameMakerProvider


def test_missing_windows_sandbox_never_reports_ready(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AI_GRADER_WINDOWS_SANDBOX", "1")
    provider = WindowsSandboxGameMakerProvider(sandbox_executable=str(tmp_path / "missing.exe"), work_root=tmp_path / "work")
    readiness = provider.readiness(executable=tmp_path / "game.exe", submission_root=tmp_path)
    assert readiness.ready is False
    assert readiness.provider_configured is False
    assert readiness.detail == "windows_sandbox_executable_not_found"


def test_flag_is_not_sufficient_without_probe_authorization(tmp_path: Path, monkeypatch):
    sandbox = tmp_path / "WindowsSandbox.exe"
    sandbox.write_bytes(b"stub")
    monkeypatch.setenv("AI_GRADER_WINDOWS_SANDBOX", "1")
    monkeypatch.delenv("AI_GRADER_WINDOWS_SANDBOX_PROBE", raising=False)
    provider = WindowsSandboxGameMakerProvider(sandbox_executable=str(sandbox), work_root=tmp_path / "work")
    readiness = provider.readiness(executable=tmp_path / "game.exe", submission_root=tmp_path)
    assert readiness.ready is False
    assert readiness.provider_configured is True
    assert readiness.provider_reachable is True
    assert readiness.disposable_environment_created is False
    assert readiness.detail == "windows_sandbox_probe_not_authorized"


def test_wsb_configuration_is_network_isolated_and_has_separate_mounts(tmp_path: Path):
    sandbox = tmp_path / "WindowsSandbox.exe"
    sandbox.write_bytes(b"stub")
    provider = WindowsSandboxGameMakerProvider(sandbox_executable=str(sandbox), work_root=tmp_path / "work")
    source, evidence = tmp_path / "source", tmp_path / "evidence"
    config = provider._write_config(source, evidence, Path("CheeseChase.exe"), 15, probe=False)
    text = config.read_text(encoding="utf-8")
    assert "<Networking>Disable</Networking>" in text
    assert "<ClipboardRedirection>Disable</ClipboardRedirection>" in text
    assert "<ReadOnly>true</ReadOnly>" in text
    assert "<ReadOnly>false</ReadOnly>" in text
    assert "windows_sandbox_guest_runner.ps1" in text


def test_builtin_provider_selection_does_not_enable_host_execution(monkeypatch):
    from app.runtime_engines.gamemaker.sandbox_provider import resolve_gamemaker_sandbox_provider
    monkeypatch.setenv("AI_GRADER_WINDOWS_SANDBOX", "1")
    monkeypatch.setenv("AI_GRADER_GAMEMAKER_SANDBOX_PROVIDER", "windows-sandbox")
    monkeypatch.delenv("AI_GRADER_GAMEMAKER_SANDBOX_ADAPTER", raising=False)
    provider, readiness = resolve_gamemaker_sandbox_provider()
    assert provider is not None
    assert readiness.ready is False
    assert readiness.provider_configured is True
