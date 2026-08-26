from __future__ import annotations

import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.runtime_engines.gamemaker.project_probe import GameMakerLayout
from app.runtime_engines.gamemaker import runtime_verification as rv


def main() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        project = root / "student" / "V2"
        project.mkdir(parents=True)
        yyp = project / "Game.yyp"
        yyp.write_text("{}", encoding="utf-8")
        (project / "player.gml").write_text("keyboard_check(vk_right);", encoding="utf-8")
        workspace = root / "workspace"
        fake_igor = root / "Igor.exe"
        fake_runtime = root / "runtime"
        fake_igor.write_bytes(b"MZ")
        fake_runtime.mkdir()
        toolchain = SimpleNamespace(
            ready=True,
            reason="ready",
            igor_path=fake_igor,
            user_folder=root / "user",
            runtime_root=fake_runtime,
            to_dict=lambda: {
                "installed": True,
                "ready": True,
                "igor_path": str(fake_igor),
                "runtime_root": str(fake_runtime),
            },
        )
        layout = GameMakerLayout(
            project_root=project,
            yyp_path=yyp,
            gml_files=[project / "player.gml"],
        )
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            calls.append([str(item) for item in cmd])
            out_dir = workspace / "ide_build"
            out_dir.mkdir(parents=True, exist_ok=True)
            package = out_dir / "gamemaker_windows_build.zip"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("Game.exe", b"MZ")
            return subprocess.CompletedProcess(cmd, 0, stdout="Igor OK", stderr="")

        before = {"module": str(rv.__file__), "layout_yyp_before": str(layout.yyp_path), "workspace": str(workspace)}
        with patch.object(rv, "discover_gamemaker_toolchain", return_value=toolchain), patch.object(
            rv.subprocess, "run", side_effect=fake_run
        ):
            result = rv.run_build_pipeline(layout, workspace=workspace, timeout_seconds=30)

        print(json.dumps({"trace": before, "layout_yyp_after": str(layout.yyp_path), "igor_command_before_assertions": calls}, default=str, ensure_ascii=False))
        assert calls, "The source-only pipeline did not invoke Igor"
        assert calls[0][0] == str(fake_igor)
        assert any(item.lower().startswith("/project=") and item.lower().endswith("game.yyp") for item in calls[0])
        assert result["ide_build_attempted"] is True
        assert result["ide_build"]["attempted"] is True
        assert result["ide_build"]["success"] is True
        assert result["ide_build"]["executable"]
        print(json.dumps({"result": result, "igor_command": calls[0]}, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
