"""Extract structured RequirementPlan from Brief/GDD/Test Plan for PRO playtesting."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.requirement_checklist import CHECKLIST_VERSION, build_requirement_checklist

EXTRACTOR_VERSION = "requirement_extractor_v1"

_REQ_LABELS_AR: Dict[str, str] = {
    "menu_navigation": "دخول اللعبة من القائمة",
    "player_movement": "حركة اللاعب",
    "player_jump": "القفز",
    "score_system": "نظام النقاط",
    "win_lose_condition": "شرط الفوز أو الخسارة",
    "collect_items": "جمع العناصر",
    "enemy_interaction": "تفاعل العدو",
}


@dataclass(frozen=True)
class InputAction:
    """Single input step in a requirement playtest sequence."""

    action: str
    key: str = ""
    duration: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {"action": self.action}
        if self.key:
            row["key"] = self.key
        if self.duration:
            row["duration"] = self.duration
        return row


@dataclass
class RequirementTest:
    req_id: str
    description: str = ""
    btec_criteria: List[str] = field(default_factory=list)
    input_sequence: List[InputAction] = field(default_factory=list)
    verification_method: str = ""
    success_threshold: float = 0.0
    required_for_gate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "description": self.description,
            "btec_criteria": list(self.btec_criteria),
            "input_sequence": [a.to_dict() for a in self.input_sequence],
            "verification_method": self.verification_method,
            "success_threshold": self.success_threshold,
            "required_for_gate": self.required_for_gate,
        }


@dataclass
class RequirementPlan:
    submission_id: str = ""
    engine: str = "godot"
    requirements: List[RequirementTest] = field(default_factory=list)
    extracted_from: List[str] = field(default_factory=list)
    extraction_confidence: float = 0.0
    version: str = EXTRACTOR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "submission_id": self.submission_id,
            "engine": self.engine,
            "requirements": [r.to_dict() for r in self.requirements],
            "extracted_from": list(self.extracted_from),
            "extraction_confidence": self.extraction_confidence,
        }

    def requirement_ids(self) -> List[str]:
        return [r.req_id for r in self.requirements]


def _menu_navigation_test() -> RequirementTest:
    return RequirementTest(
        req_id="menu_navigation",
        description=_REQ_LABELS_AR["menu_navigation"],
        btec_criteria=[],
        input_sequence=[
            InputAction("click_center"),
            InputAction("key", "Return"),
        ],
        verification_method="scene_change",
        success_threshold=0.15,
        required_for_gate=True,
    )


def _player_movement_test() -> RequirementTest:
    return RequirementTest(
        req_id="player_movement",
        description=_REQ_LABELS_AR["player_movement"],
        btec_criteria=["C.P5"],
        input_sequence=[
            InputAction("key_hold", "d", duration=0.6),
            InputAction("key_hold", "a", duration=0.6),
        ],
        verification_method="pixel_shift_horizontal",
        success_threshold=0.03,
        required_for_gate=True,
    )


def _player_jump_test() -> RequirementTest:
    return RequirementTest(
        req_id="player_jump",
        description=_REQ_LABELS_AR["player_jump"],
        btec_criteria=["C.P5"],
        input_sequence=[InputAction("key", "space")],
        verification_method="pixel_shift_vertical",
        success_threshold=0.02,
        required_for_gate=False,
    )


def _score_system_test() -> RequirementTest:
    return RequirementTest(
        req_id="score_system",
        description=_REQ_LABELS_AR["score_system"],
        btec_criteria=["C.P5", "C.M3"],
        input_sequence=[InputAction("key_hold", "d", duration=2.0)],
        verification_method="ocr_hud_change",
        success_threshold=0.7,
        required_for_gate=False,
    )


def _win_lose_test() -> RequirementTest:
    return RequirementTest(
        req_id="win_lose_condition",
        description=_REQ_LABELS_AR["win_lose_condition"],
        btec_criteria=["C.D3"],
        input_sequence=[InputAction("key_hold", "d", duration=15.0)],
        verification_method="ocr_endgame_screen",
        success_threshold=0.7,
        required_for_gate=False,
    )


DEFAULT_GODOT_EXE_PLAN = RequirementPlan(
    engine="godot",
    requirements=[
        _menu_navigation_test(),
        _player_movement_test(),
        _player_jump_test(),
        _score_system_test(),
        _win_lose_test(),
    ],
    extraction_confidence=1.0,
)


_OPTIONAL_REQ_BUILDERS: Dict[str, Any] = {
    "collect_items": lambda: RequirementTest(
        req_id="collect_items",
        description=_REQ_LABELS_AR["collect_items"],
        btec_criteria=["C.M3"],
        input_sequence=[InputAction("key_hold", "d", duration=3.0)],
        verification_method="ocr_hud_change",
        success_threshold=0.6,
        required_for_gate=False,
    ),
    "enemy_interaction": lambda: RequirementTest(
        req_id="enemy_interaction",
        description=_REQ_LABELS_AR["enemy_interaction"],
        btec_criteria=["C.M3"],
        input_sequence=[InputAction("key_hold", "d", duration=5.0)],
        verification_method="ocr_endgame_screen",
        success_threshold=0.6,
        required_for_gate=False,
    ),
}


class RequirementExtractor:
    """Build RequirementPlan from student docs or engine defaults."""

    def extract(
        self,
        *,
        submission_id: str = "",
        engine: str = "godot",
        student_text: str = "",
        reference_solution: Optional[Dict[str, Any]] = None,
        extra_texts: Optional[Sequence[str]] = None,
        document_paths: Optional[Sequence[str]] = None,
    ) -> RequirementPlan:
        checklist = build_requirement_checklist(
            student_text=student_text,
            reference_solution=reference_solution,
            extra_texts=extra_texts,
        )
        mentioned = set(checklist.get("requirement_ids") or [])
        has_source_text = bool((student_text or "").strip()) or bool(document_paths)

        if not has_source_text:
            return RequirementPlan(
                submission_id=submission_id,
                engine=engine or "godot",
                requirements=list(DEFAULT_GODOT_EXE_PLAN.requirements),
                extracted_from=list(document_paths or []),
                extraction_confidence=1.0,
            )

        base = list(DEFAULT_GODOT_EXE_PLAN.requirements)
        optional_ids = ("collect_items", "enemy_interaction")
        for opt_id in optional_ids:
            if opt_id in mentioned and opt_id in _OPTIONAL_REQ_BUILDERS:
                base.append(_OPTIONAL_REQ_BUILDERS[opt_id]())

        confidence = 0.85 if mentioned else 0.6
        if document_paths:
            confidence = min(0.95, confidence + 0.05)

        return RequirementPlan(
            submission_id=submission_id,
            engine=engine or "godot",
            requirements=base,
            extracted_from=list(document_paths or []),
            extraction_confidence=confidence,
        )

    def default_plan(
        self,
        *,
        submission_id: str = "",
        engine: str = "godot",
    ) -> RequirementPlan:
        return RequirementPlan(
            submission_id=submission_id,
            engine=engine,
            requirements=list(DEFAULT_GODOT_EXE_PLAN.requirements),
            extracted_from=[],
            extraction_confidence=1.0,
        )


def plan_from_checklist(
    checklist: Dict[str, Any],
    *,
    submission_id: str = "",
    engine: str = "godot",
) -> RequirementPlan:
    """Bridge from legacy checklist v1 to RequirementPlan."""
    _ = checklist.get("version", CHECKLIST_VERSION)
    return RequirementExtractor().extract(
        submission_id=submission_id,
        engine=engine,
        student_text=" ".join(checklist.get("requirement_ids") or []),
    )
