"""Runtime engine registry and resolution."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Type

from app.runtime_engines.base import RuntimeEngine

_ENGINE_REGISTRY: List[Type[RuntimeEngine]] = []


def register_engine(engine_cls: Type[RuntimeEngine]) -> Type[RuntimeEngine]:
    if engine_cls not in _ENGINE_REGISTRY:
        _ENGINE_REGISTRY.append(engine_cls)
    return engine_cls


_BUILTIN_ENGINES_LOADED = False


def get_engine_registry() -> List[Type[RuntimeEngine]]:
    _ensure_builtin_engines()
    return list(_ENGINE_REGISTRY)


def _ensure_builtin_engines() -> None:
    global _BUILTIN_ENGINES_LOADED
    if _BUILTIN_ENGINES_LOADED:
        return
    _load_builtin_engines()
    _BUILTIN_ENGINES_LOADED = True


def _load_builtin_engines() -> None:
    from app.runtime_engines.web.engine import WebRuntimeEngine
    from app.runtime_engines.android.engine import AndroidRuntimeEngine
    from app.runtime_engines.godot.engine import GodotRuntimeEngine
    from app.runtime_engines.gamemaker.engine import GameMakerRuntimeEngine
    from app.runtime_engines.scratch.engine import ScratchRuntimeEngine
    from app.runtime_engines.unity.engine import UnityRuntimeEngine
    from app.runtime_engines.legacy.engine import LegacyExecutableEngine

    for cls in (
        UnityRuntimeEngine,
        AndroidRuntimeEngine,
        ScratchRuntimeEngine,
        GameMakerRuntimeEngine,
        GodotRuntimeEngine,
        WebRuntimeEngine,
        LegacyExecutableEngine,
    ):
        register_engine(cls)


def resolve_engine(root: Path) -> Optional[Type[RuntimeEngine]]:
    _ensure_builtin_engines()
    registry = get_engine_registry()
    scored = [(cls, cls.detect(root)) for cls in registry]
    scored = [(cls, score) for cls, score in scored if score > 0.3]
    if not scored:
        return None
    return max(scored, key=lambda item: item[1])[0]
