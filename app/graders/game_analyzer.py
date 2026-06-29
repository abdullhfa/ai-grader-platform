"""
Game Development Code Analyzer for BTEC Grading
=================================================
Detects and analyzes game projects from Unity (C#), GameMaker (GML),
Godot (GDScript), and Scratch (.sb3 JSON) in student submissions.

Four engine modes:
  1. Unity / C#       — MonoBehaviour scripts, scene logic, physics, UI
  2. GameMaker GML    — objects, events, draw/step, sprites, rooms
  3. Godot / GDScript — nodes, scenes, signals, physics, UI
  4. Scratch          — .sb3 JSON blocks, sprites, costumes, sounds

Static analysis is always available; optional SDK execution for Unity.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════
# Detection Patterns
# ═══════════════════════════════════════════════════════

_UNITY_INDICATORS = [
    r'\busing\s+UnityEngine\b',
    r'\busing\s+UnityEngine\.\w+\b',
    r'\bMonoBehaviour\b',
    r'\bGameObject\b',
    r'\bTransform\b',
    r'\bRigidbody(?:2D)?\b',
    r'\bCollider(?:2D)?\b',
    r'\bvoid\s+Start\s*\(\s*\)',
    r'\bvoid\s+Update\s*\(\s*\)',
    r'\bvoid\s+Awake\s*\(\s*\)',
    r'\bvoid\s+FixedUpdate\s*\(\s*\)',
    r'\bvoid\s+LateUpdate\s*\(\s*\)',
    r'\bvoid\s+OnCollisionEnter',
    r'\bvoid\s+OnTriggerEnter',
    r'\bInstantiate\s*\(',
    r'\bDestroy\s*\(',
    r'\bGetComponent\s*<',
    r'\bInput\.GetKey',
    r'\bInput\.GetAxis',
    r'\bInput\.GetButton',
    r'\bVector[23]\b',
    r'\bQuaternion\b',
    r'\bTime\.deltaTime\b',
    r'\bSceneManager\b',
    r'\bSerializeField\b',
    r'\bCoroutine\b',
    r'\bStartCoroutine\b',
    r'\byield\s+return\b',
    r'\bAnimator\b',
    r'\bAudioSource\b',
    r'\bCanvas\b',
    r'\bUI\.\w+\b',
    r'\bNavMeshAgent\b',
    r'\bParticleSystem\b',
]

_CSHARP_INDICATORS = [
    r'\busing\s+System\b',
    r'\bnamespace\s+\w+',
    r'\bclass\s+\w+\s*:\s*\w+',
    r'\bpublic\s+(void|int|float|string|bool|static)',
    r'\bprivate\s+\w+',
    r'\bprotected\s+\w+',
    r'\b\[SerializeField\]',
    r'\b\[Header\(',
    r'\b\[RequireComponent\(',
    r'\bnew\s+\w+\s*\(',
    r'\bforeach\s*\(',
    r'\bDebug\.Log\s*\(',
]

_GAMEMAKER_INDICATORS = [
    r'\bdraw_sprite\b',
    r'\bdraw_text\b',
    r'\bdraw_rectangle\b',
    r'\bdraw_circle\b',
    r'\bdraw_self\b',
    r'\binstance_create\b',
    r'\binstance_destroy\b',
    r'\bplace_meeting\b',
    r'\bpoint_direction\b',
    r'\bpoint_distance\b',
    r'\blengthdir_[xy]\b',
    r'\bkeyboard_check\b',
    r'\bmouse_check_button\b',
    r'\bvk_\w+\b',
    r'\broom_goto\b',
    r'\broom_restart\b',
    r'\bgame_restart\b',
    r'\bgame_end\b',
    r'\bobj_\w+\b',
    r'\bspr_\w+\b',
    r'\brm_\w+\b',
    r'\bsprite_index\b',
    r'\bimage_speed\b',
    r'\bimage_index\b',
    r'\bimage_xscale\b',
    r'\bimage_yscale\b',
    r'\bglobal\.\w+\b',
    r'\bspeed\b',
    r'\bdirection\b',
    r'\bhspeed\b',
    r'\bvspeed\b',
    r'\bgravity\b',
    r'\bfriction\b',
    r'\balarm\[\d+\]',
    r'\birandom\b',
    r'\brandom_range\b',
    r'\bscr_\w+\b',
    r'\bshow_message\b',
    r'\baudio_play_sound\b',
    r'\bsurface_\w+\b',
    r'\bds_list_\w+\b',
    r'\bds_map_\w+\b',
    r'\bwith\s*\(\s*\w+\s*\)',
    r'\b///\s*@desc',
    r'\bevent_inherited\b',
    r'\bother\.\w+',
]

_GODOT_INDICATORS = [
    r'\bextends\s+\w+',
    r'\bclass_name\s+\w+',
    r'\bfunc\s+_\w+',
    r'\b@onready\b',
    r'\b@export\b',
    r'\btween\b|\bTween\b',
    r'\bsignal\b',
    r'\bawait\b',
    r'\bpreload\s*\(',
    r'\bmove_and_slide\b',
    r'\bCharacterBody(?:2D|3D)?\b',
    r'\bRigidBody(?:2D|3D)?\b',
    r'\bArea(?:2D|3D)?\b',
    r'\bCollision(?:Shape|Polygon)(?:2D|3D)?\b',
    r'\bAnimatedSprite\d?\b',
    r'\bAnimationPlayer\b',
    r'\bTileMap(?:Layer)?\b',
    r'\bget_tree\s*\(\s*\)',
    r'\bchange_scene(?:_to_(?:packed|file))?\b',
    r'\bInput\.(?:is_action|get_axis|get_vector)\b',
    r'\bdelta\b',
]

_SCRATCH_BLOCK_TYPES = [
    "motion_movesteps", "motion_turnright", "motion_turnleft",
    "motion_gotoxy", "motion_glideto", "motion_changexby",
    "motion_changeyby", "motion_setx", "motion_sety",
    "looks_say", "looks_sayforsecs", "looks_think",
    "looks_switchcostumeto", "looks_nextcostume",
    "looks_changesizeby", "looks_setsizeto",
    "looks_show", "looks_hide",
    "sound_playuntildone", "sound_play", "sound_stopallsounds",
    "event_whenflagclicked", "event_whenkeypressed",
    "event_whenthisspriteclicked", "event_whenbroadcastreceived",
    "event_broadcast", "event_broadcastandwait",
    "control_wait", "control_repeat", "control_forever",
    "control_if", "control_if_else", "control_wait_until",
    "control_repeat_until", "control_stop",
    "control_create_clone_of", "control_delete_this_clone",
    "sensing_touchingobject", "sensing_touchingcolor",
    "sensing_distanceto", "sensing_askandwait", "sensing_answer",
    "sensing_keypressed", "sensing_mousedown",
    "sensing_mousex", "sensing_mousey",
    "operator_add", "operator_subtract", "operator_multiply",
    "operator_divide", "operator_random",
    "operator_gt", "operator_lt", "operator_equals",
    "operator_and", "operator_or", "operator_not",
    "operator_join", "operator_letter_of", "operator_length",
    "data_setvariableto", "data_changevariableby",
    "data_addtolist", "data_deleteoflist", "data_lengthoflist",
    "procedures_definition", "procedures_call",
]

# Unity component categories for assessment
_UNITY_COMPONENT_CATEGORIES = {
    "lifecycle": [
        "Awake", "Start", "Update", "FixedUpdate", "LateUpdate",
        "OnEnable", "OnDisable", "OnDestroy",
    ],
    "physics": [
        "Rigidbody", "Rigidbody2D", "Collider", "Collider2D",
        "OnCollisionEnter", "OnCollisionExit", "OnCollisionStay",
        "OnTriggerEnter", "OnTriggerExit", "OnTriggerStay",
        "AddForce", "velocity", "MovePosition",
        "OnCollisionEnter2D", "OnCollisionExit2D",
        "OnTriggerEnter2D", "OnTriggerExit2D",
    ],
    "input": [
        "Input.GetKey", "Input.GetKeyDown", "Input.GetKeyUp",
        "Input.GetAxis", "Input.GetButton", "Input.GetMouseButton",
        "Input.mousePosition", "Input.GetTouch",
    ],
    "rendering": [
        "SpriteRenderer", "MeshRenderer", "LineRenderer",
        "ParticleSystem", "Camera", "Light",
        "Material", "Shader", "Texture",
    ],
    "audio": [
        "AudioSource", "AudioClip", "AudioListener",
        "PlayOneShot", "AudioMixer",
    ],
    "ui": [
        "Canvas", "Button", "Text", "Image", "Slider",
        "Toggle", "InputField", "Panel", "ScrollRect",
        "TextMeshPro", "TMP_Text",
    ],
    "animation": [
        "Animator", "Animation", "AnimationClip",
        "SetTrigger", "SetBool", "SetFloat", "SetInteger",
    ],
    "scene_management": [
        "SceneManager", "LoadScene", "LoadSceneAsync",
        "DontDestroyOnLoad",
    ],
    "ai_navigation": [
        "NavMeshAgent", "NavMesh", "NavMeshPath",
        "SetDestination",
    ],
    "coroutines": [
        "StartCoroutine", "StopCoroutine", "yield",
        "WaitForSeconds", "WaitForEndOfFrame", "WaitUntil",
    ],
}

# GameMaker concept categories
_GAMEMAKER_CATEGORIES = {
    "movement": [
        "speed", "direction", "hspeed", "vspeed",
        "move_towards_point", "motion_set", "path_start",
        "mp_grid", "mp_potential",
    ],
    "drawing": [
        "draw_sprite", "draw_text", "draw_rectangle", "draw_circle",
        "draw_line", "draw_self", "draw_surface",
        "draw_set_color", "draw_set_font", "draw_set_alpha",
    ],
    "collision": [
        "place_meeting", "place_free", "collision_point",
        "collision_line", "collision_rectangle",
        "instance_place", "position_meeting",
    ],
    "instances": [
        "instance_create", "instance_create_layer",
        "instance_destroy", "instance_exists",
        "instance_number", "instance_find",
    ],
    "input": [
        "keyboard_check", "keyboard_check_pressed", "keyboard_check_released",
        "mouse_check_button", "mouse_check_button_pressed",
        "mouse_x", "mouse_y",
    ],
    "rooms": [
        "room_goto", "room_goto_next", "room_goto_previous",
        "room_restart", "game_restart", "game_end",
    ],
    "audio": [
        "audio_play_sound", "audio_stop_sound", "audio_is_playing",
        "audio_sound_gain",
    ],
    "data_structures": [
        "ds_list", "ds_map", "ds_grid", "ds_stack", "ds_queue",
        "array", "json_encode", "json_decode",
    ],
    "sprites_animation": [
        "sprite_index", "image_speed", "image_index",
        "image_xscale", "image_yscale", "image_angle",
        "image_blend", "image_alpha",
    ],
}

# Scratch block categories
_SCRATCH_CATEGORIES = {
    "motion": [
        "motion_movesteps", "motion_turnright", "motion_turnleft",
        "motion_gotoxy", "motion_glideto", "motion_changexby",
        "motion_changeyby", "motion_setx", "motion_sety",
        "motion_pointindirection", "motion_pointtowards",
        "motion_ifonedgebounce",
    ],
    "looks": [
        "looks_say", "looks_sayforsecs", "looks_think",
        "looks_switchcostumeto", "looks_nextcostume",
        "looks_changesizeby", "looks_setsizeto",
        "looks_show", "looks_hide", "looks_switchbackdropto",
        "looks_changeeffectby", "looks_seteffectto",
    ],
    "sound": [
        "sound_playuntildone", "sound_play", "sound_stopallsounds",
        "sound_changevolumeby", "sound_setvolumeto",
    ],
    "events": [
        "event_whenflagclicked", "event_whenkeypressed",
        "event_whenthisspriteclicked", "event_whenbroadcastreceived",
        "event_broadcast", "event_broadcastandwait",
        "event_whenbackdropswitchesto",
    ],
    "control": [
        "control_wait", "control_repeat", "control_forever",
        "control_if", "control_if_else", "control_wait_until",
        "control_repeat_until", "control_stop",
        "control_create_clone_of", "control_delete_this_clone",
        "control_start_as_clone",
    ],
    "sensing": [
        "sensing_touchingobject", "sensing_touchingcolor",
        "sensing_distanceto", "sensing_askandwait", "sensing_answer",
        "sensing_keypressed", "sensing_mousedown",
        "sensing_mousex", "sensing_mousey", "sensing_timer",
    ],
    "operators": [
        "operator_add", "operator_subtract", "operator_multiply",
        "operator_divide", "operator_random",
        "operator_gt", "operator_lt", "operator_equals",
        "operator_and", "operator_or", "operator_not",
        "operator_join", "operator_letter_of", "operator_length",
        "operator_mod", "operator_round", "operator_mathop",
    ],
    "variables": [
        "data_setvariableto", "data_changevariableby",
        "data_showvariable", "data_hidevariable",
        "data_addtolist", "data_deleteoflist",
        "data_insertatlist", "data_replaceitemoflist",
        "data_lengthoflist", "data_itemoflist",
    ],
    "custom_blocks": [
        "procedures_definition", "procedures_call",
        "procedures_prototype", "argument_reporter_string_number",
        "argument_reporter_boolean",
    ],
}


# ═══════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════

class GameCodeBlock:
    """Represents an extracted game code block."""

    def __init__(self, code: str, engine: str, context: str = "", line_start: int = 0):
        self.code = code
        self.engine = engine  # "unity", "gamemaker", "godot", "scratch"
        self.context = context
        self.line_start = line_start

    def __repr__(self):
        return f"<{self.engine} code block, {len(self.code)} chars>"


class GameAnalysisResult:
    """Result of game project code analysis."""

    def __init__(self):
        self.has_code = False
        self.engine = ""  # "unity", "gamemaker", "godot", "scratch"
        self.code_blocks: List[GameCodeBlock] = []
        self.total_lines = 0
        self.components_used: Dict[str, List[str]] = {}
        self.game_features: List[str] = []
        self.structure_score = 0.0
        self.complexity_score = 0.0
        self.completeness_score = 0.0
        self.gameplay_elements: Dict[str, Any] = {}
        self.quality_notes: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.execution_result: Optional[Dict] = None
        # Scratch-specific
        self.scratch_project: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_code": self.has_code,
            "engine": self.engine,
            "code_blocks_count": len(self.code_blocks),
            "total_lines": self.total_lines,
            "components_used": self.components_used,
            "game_features": self.game_features,
            "structure_score": round(self.structure_score, 2),
            "complexity_score": round(self.complexity_score, 2),
            "completeness_score": round(self.completeness_score, 2),
            "gameplay_elements": self.gameplay_elements,
            "quality_notes": self.quality_notes,
            "errors": self.errors,
            "warnings": self.warnings,
            "execution_result": self.execution_result,
            "scratch_project": self.scratch_project,
            "summary_ar": self._summary_ar(),
            "summary_en": self._summary_en(),
        }

    def _summary_ar(self) -> str:
        if not self.has_code:
            return "لم يتم العثور على كود لعبة (Unity/GameMaker/Godot/Scratch) في التقديم"
        engine_names = {"unity": "Unity (C#)", "gamemaker": "GameMaker (GML)", "godot": "Godot (GDScript)", "scratch": "Scratch"}
        name = engine_names.get(self.engine, self.engine)
        parts = [f"تم العثور على مشروع {name}"]
        if self.engine == "scratch":
            if self.scratch_project:
                sprites = self.scratch_project.get("sprite_count", 0)
                parts.append(f"عدد الشخصيات: {sprites}")
        else:
            parts.append(f"{len(self.code_blocks)} كتلة كود")
            parts.append(f"إجمالي الأسطر: {self.total_lines}")
        comp_count = sum(len(v) for v in self.components_used.values())
        if comp_count:
            parts.append(f"عناصر مستخدمة: {comp_count}")
        if self.game_features:
            parts.append(f"خصائص اللعبة: {len(self.game_features)}")
        if self.errors:
            parts.append(f"أخطاء: {len(self.errors)}")
        parts.append(f"جودة الهيكل: {self.structure_score:.0%}")
        parts.append(f"التعقيد: {self.complexity_score:.0%}")
        parts.append(f"الاكتمال: {self.completeness_score:.0%}")
        return " | ".join(parts)

    def _summary_en(self) -> str:
        if not self.has_code:
            return "No game code (Unity/GameMaker/Godot/Scratch) found in submission"
        engine_names = {"unity": "Unity (C#)", "gamemaker": "GameMaker (GML)", "godot": "Godot (GDScript)", "scratch": "Scratch"}
        name = engine_names.get(self.engine, self.engine)
        parts = [f"Found {name} project"]
        if self.engine == "scratch":
            if self.scratch_project:
                sprites = self.scratch_project.get("sprite_count", 0)
                parts.append(f"Sprites: {sprites}")
        else:
            parts.append(f"{len(self.code_blocks)} code block(s)")
            parts.append(f"Total lines: {self.total_lines}")
        comp_count = sum(len(v) for v in self.components_used.values())
        if comp_count:
            parts.append(f"Components: {comp_count}")
        if self.game_features:
            parts.append(f"Game features: {len(self.game_features)}")
        if self.errors:
            parts.append(f"Errors: {len(self.errors)}")
        parts.append(f"Structure: {self.structure_score:.0%}")
        parts.append(f"Complexity: {self.complexity_score:.0%}")
        parts.append(f"Completeness: {self.completeness_score:.0%}")
        return " | ".join(parts)


# ═══════════════════════════════════════════════════════
# Main Analyzer Class
# ═══════════════════════════════════════════════════════

class GameCodeAnalyzer:
    """
    Analyzes game project code from Unity, GameMaker, Godot, and Scratch.
    """

    # ─── Public Entry Points ────────────────────────────

    @staticmethod
    def detect_and_analyze(text: str) -> GameAnalysisResult:
        """
        Main entry point: detect game code in text, analyze it.
        Text may be extracted from .docx/.pdf (containing code)
        or from raw code files (.cs, .gml).
        """
        result = GameAnalysisResult()

        # Try Unity / C# first (most common BTEC game assignments)
        code_blocks = GameCodeAnalyzer._extract_unity_blocks(text)
        if code_blocks:
            result.engine = "unity"
            result.has_code = True
            result.code_blocks = code_blocks
            all_code = "\n\n".join(b.code for b in code_blocks)
            result.total_lines = sum(len(b.code.splitlines()) for b in code_blocks)
            result.components_used = GameCodeAnalyzer._detect_unity_components(all_code)
            result.game_features = GameCodeAnalyzer._detect_unity_features(all_code)
            result.structure_score = GameCodeAnalyzer._assess_unity_structure(all_code, code_blocks)
            result.complexity_score = GameCodeAnalyzer._assess_unity_complexity(all_code)
            result.completeness_score = GameCodeAnalyzer._assess_unity_completeness(all_code, result)
            result.gameplay_elements = GameCodeAnalyzer._detect_gameplay_elements(all_code, "unity")
            result.quality_notes = GameCodeAnalyzer._check_unity_quality(all_code)
            result.errors = GameCodeAnalyzer._detect_csharp_syntax_issues(all_code)
            result.warnings = GameCodeAnalyzer._detect_unity_warnings(all_code)
            execution = GameCodeAnalyzer._try_execute_unity(all_code)
            if execution:
                result.execution_result = execution
            return result

        # Try GameMaker GML
        code_blocks = GameCodeAnalyzer._extract_gamemaker_blocks(text)
        if code_blocks:
            result.engine = "gamemaker"
            result.has_code = True
            result.code_blocks = code_blocks
            all_code = "\n\n".join(b.code for b in code_blocks)
            result.total_lines = sum(len(b.code.splitlines()) for b in code_blocks)
            result.components_used = GameCodeAnalyzer._detect_gamemaker_components(all_code)
            result.game_features = GameCodeAnalyzer._detect_gamemaker_features(all_code)
            result.structure_score = GameCodeAnalyzer._assess_gamemaker_structure(all_code, code_blocks)
            result.complexity_score = GameCodeAnalyzer._assess_gamemaker_complexity(all_code)
            result.completeness_score = GameCodeAnalyzer._assess_gamemaker_completeness(all_code, result)
            result.gameplay_elements = GameCodeAnalyzer._detect_gameplay_elements(all_code, "gamemaker")
            result.quality_notes = GameCodeAnalyzer._check_gamemaker_quality(all_code)
            result.errors = GameCodeAnalyzer._detect_gml_syntax_issues(all_code)
            result.warnings = GameCodeAnalyzer._detect_gamemaker_warnings(all_code)
            return result

        # Try Godot (GDScript)
        code_blocks = GameCodeAnalyzer._extract_godot_blocks(text)
        if code_blocks:
            result.engine = "godot"
            result.has_code = True
            result.code_blocks = code_blocks
            all_code = "\n\n".join(b.code for b in code_blocks)
            result.total_lines = sum(len(b.code.splitlines()) for b in code_blocks)
            result.components_used = GameCodeAnalyzer._detect_godot_components(all_code)
            result.game_features = GameCodeAnalyzer._detect_godot_features(all_code)
            result.structure_score = GameCodeAnalyzer._assess_godot_structure(all_code, code_blocks)
            result.complexity_score = GameCodeAnalyzer._assess_godot_complexity(all_code)
            result.completeness_score = GameCodeAnalyzer._assess_godot_completeness(all_code, result)
            result.gameplay_elements = GameCodeAnalyzer._detect_gameplay_elements(all_code, "godot")
            result.quality_notes = GameCodeAnalyzer._check_godot_quality(all_code)
            result.warnings = GameCodeAnalyzer._detect_godot_warnings(all_code)
            return result

        return result

    @staticmethod
    def analyze_scratch_file(sb3_path: str) -> GameAnalysisResult:
        """
        Analyze a Scratch .sb3 file (it's a ZIP containing project.json).
        """
        result = GameAnalysisResult()

        try:
            if not os.path.exists(sb3_path):
                return result

            with zipfile.ZipFile(sb3_path, 'r') as zf:
                if 'project.json' not in zf.namelist():
                    return result
                project_data = json.loads(zf.read('project.json').decode('utf-8'))
        except (zipfile.BadZipFile, json.JSONDecodeError, Exception) as e:
            result.errors.append(f"فشل فتح ملف Scratch: {e}")
            return result

        result.has_code = True
        result.engine = "scratch"

        # Parse project structure
        targets = project_data.get("targets", [])
        stage = None
        sprites = []
        for target in targets:
            if target.get("isStage"):
                stage = target
            else:
                sprites.append(target)

        # Collect all blocks across all targets
        all_blocks: Dict[str, Any] = {}
        for target in targets:
            blocks = target.get("blocks", {})
            if isinstance(blocks, dict):
                all_blocks.update(blocks)

        # Build project summary
        project_info: Dict[str, Any] = {
            "sprite_count": len(sprites),
            "sprite_names": [s.get("name", "?") for s in sprites],
            "stage_backdrops": len(stage.get("costumes", [])) if stage else 0,
            "total_blocks": len(all_blocks),
            "total_costumes": sum(len(t.get("costumes", [])) for t in targets),
            "total_sounds": sum(len(t.get("sounds", [])) for t in targets),
            "total_variables": len(project_data.get("monitors", [])),
        }

        # Count variables and lists across targets
        var_count = 0
        list_count = 0
        for target in targets:
            var_count += len(target.get("variables", {}))
            list_count += len(target.get("lists", {}))
        project_info["variables"] = var_count
        project_info["lists"] = list_count

        result.scratch_project = project_info
        result.total_lines = len(all_blocks)  # blocks ≈ "lines" in Scratch

        # Categorize blocks
        result.components_used = GameCodeAnalyzer._categorize_scratch_blocks(all_blocks)

        # Detect game features
        result.game_features = GameCodeAnalyzer._detect_scratch_features(all_blocks, targets)

        # Scoring
        result.structure_score = GameCodeAnalyzer._assess_scratch_structure(project_info, all_blocks, targets)
        result.complexity_score = GameCodeAnalyzer._assess_scratch_complexity(all_blocks, targets)
        result.completeness_score = GameCodeAnalyzer._assess_scratch_completeness(project_info, all_blocks, result)
        result.gameplay_elements = GameCodeAnalyzer._detect_gameplay_elements_scratch(all_blocks, targets)
        result.quality_notes = GameCodeAnalyzer._check_scratch_quality(project_info, all_blocks, targets)
        result.warnings = GameCodeAnalyzer._detect_scratch_warnings(project_info, all_blocks)

        return result

    # ═══════════════════════════════════════════════════
    # UNITY / C# Methods
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _extract_unity_blocks(text: str) -> List[GameCodeBlock]:
        """Extract Unity C# code blocks from text."""
        blocks: List[GameCodeBlock] = []

        # If the full text looks like C#/Unity code
        if GameCodeAnalyzer._is_mostly_code(text) and GameCodeAnalyzer._is_unity_code(text):
            return [GameCodeBlock(text.strip(), "unity", "full_text")]

        # Markdown fences: ```csharp or ```cs or ```c#
        fence_pattern = re.compile(
            r'```(?:csharp|cs|c#)?\s*\n(.*?)```',
            re.DOTALL | re.IGNORECASE,
        )
        for match in fence_pattern.finditer(text):
            code = match.group(1).strip()
            if code and GameCodeAnalyzer._is_unity_code(code):
                blocks.append(GameCodeBlock(code, "unity", "markdown_fence"))

        remaining = fence_pattern.sub('', text)

        # Look for C# class definitions with Unity patterns
        class_pattern = re.compile(
            r'((?:using\s+\w[\w.]*;\s*\n)*\s*'
            r'(?:(?:public|private|internal)\s+)?class\s+\w+'
            r'(?:\s*:\s*[\w<>,\s]+)?\s*\{.*?\n\})',
            re.DOTALL,
        )
        for match in class_pattern.finditer(remaining):
            code = match.group(0).strip()
            if len(code) > 80 and GameCodeAnalyzer._is_unity_code(code):
                if not any(code[:60] in b.code for b in blocks):
                    blocks.append(GameCodeBlock(code, "unity", "class_definition"))

        # Inline code detection
        _CODE_LINE = (
            r'[ \t]*(?:using\s|public\s|private\s|protected\s|void\s|int\s|float\s|'
            r'string\s|bool\s|class\s|if\s*\(|for\s*\(|foreach\s*\(|while\s*\(|'
            r'return\s|//|}\s*$|{\s*$|\[\w|var\s|new\s|this\.|base\.|'
            r'Debug\.Log|GetComponent|Transform|GameObject|Input\.|'
            r'Vector[23]|Quaternion|Rigidbody|Collider|'
            r'\w+\s*\(|[\w<>]+\s+\w+\s*[=;])'
        )
        code_region_pattern = re.compile(
            r'((?:^' + _CODE_LINE + r'.*$\n?(?:\s*\n){0,2}){3,})',
            re.MULTILINE,
        )
        for match in code_region_pattern.finditer(remaining):
            code = match.group(0).strip()
            if len(code) > 50 and GameCodeAnalyzer._is_unity_code(code):
                if not any(code[:60] in b.code for b in blocks):
                    blocks.append(GameCodeBlock(code, "unity", "inline_detected"))

        # Fallback: if no blocks found but text has Unity patterns
        if not blocks and len(remaining.strip()) > 50:
            if GameCodeAnalyzer._is_unity_code(remaining):
                blocks.append(GameCodeBlock(remaining.strip(), "unity", "full_text"))

        return blocks

    @staticmethod
    def _is_unity_code(text: str) -> bool:
        """Check if text looks like Unity C# code."""
        score = 0
        for pattern in _UNITY_INDICATORS:
            if re.search(pattern, text):
                score += 1
        # Also check basic C#
        for pattern in _CSHARP_INDICATORS:
            if re.search(pattern, text):
                score += 0.5
        return score >= 3

    @staticmethod
    def _detect_unity_components(code: str) -> Dict[str, List[str]]:
        """Detect Unity components used, categorized."""
        found: Dict[str, List[str]] = {}
        for category, components in _UNITY_COMPONENT_CATEGORIES.items():
            hits = []
            for comp in components:
                pattern = r'\b' + re.escape(comp) + r'\b'
                if re.search(pattern, code):
                    hits.append(comp)
            if hits:
                found[category] = hits
        return found

    @staticmethod
    def _detect_unity_features(code: str) -> List[str]:
        """Detect Unity-specific features used."""
        features = []
        feature_patterns = {
            "physics_2d": r'\bRigidbody2D\b|\bCollider2D\b|\bOnCollision\w+2D\b',
            "physics_3d": r'\bRigidbody\b(?!2D)|\bCollider\b(?!2D)|\bOnCollision\w+\b(?!2D)',
            "player_input": r'\bInput\.Get(?:Key|Axis|Button|Mouse)',
            "new_input_system": r'\bPlayerInput\b|\bInputAction\b',
            "animation": r'\bAnimator\b|\bAnimation\b|\bSetTrigger\b|\bSetBool\b',
            "audio": r'\bAudioSource\b|\bPlayOneShot\b|\bAudioClip\b',
            "ui_system": r'\bCanvas\b|\bButton\b.*onClick|\bText\b.*GetComponent',
            "scene_management": r'\bSceneManager\b|\bLoadScene\b',
            "coroutines": r'\bStartCoroutine\b|\byield\s+return\b|\bWaitForSeconds\b',
            "scriptable_objects": r'\bScriptableObject\b|\bCreateAssetMenu\b',
            "singleton_pattern": r'\bstatic\s+\w+\s+Instance\b|\bDontDestroyOnLoad\b',
            "object_pooling": r'\bPool\b|\bSetActive\s*\(\s*(?:true|false)\s*\)',
            "raycasting": r'\bRaycast\b|\bPhysics\.Raycast\b|\bPhysics2D\.Raycast\b',
            "tilemap": r'\bTilemap\b|\bTile\b',
            "navmesh": r'\bNavMeshAgent\b|\bSetDestination\b',
            "particle_system": r'\bParticleSystem\b|\bEmit\b',
            "serialization": r'\bSerializeField\b|\bSerializable\b',
            "events_delegates": r'\bUnityEvent\b|\bAction\b|\bdelegate\b|\bevent\s+',
            "spawn_system": r'\bInstantiate\b.*\bPrefab\b|\bInstantiate\b',
            "destroy_system": r'\bDestroy\b\s*\(|\bDestroyImmediate\b',
            "tags_layers": r'\bCompareTag\b|\btag\s*==\s*"|\.tag\b',
            "score_system": r'\bscore\b|\bScore\b|\bpoints\b|\bPoints\b',
            "health_system": r'\bhealth\b|\bHealth\b|\bHP\b|\bhp\b|\bdamage\b|\bDamage\b',
            "timer": r'\bTime\.time\b|\bTime\.deltaTime\b|\btimer\b|\bTimer\b|\bcountdown\b',
            "save_load": r'\bPlayerPrefs\b|\bJsonUtility\b|\bFile\.Write\b',
        }
        for feature, pattern in feature_patterns.items():
            if re.search(pattern, code, re.IGNORECASE):
                features.append(feature)
        return features

    @staticmethod
    def _assess_unity_structure(code: str, blocks: List[GameCodeBlock]) -> float:
        """Assess Unity code structure quality (0.0 - 1.0)."""
        score = 0.0
        max_score = 0.0

        # Has using statements
        max_score += 1
        if re.search(r'\busing\s+', code):
            score += 1

        # Has MonoBehaviour class
        max_score += 1
        if re.search(r':\s*MonoBehaviour\b', code):
            score += 1

        # Has lifecycle methods (Start, Update)
        max_score += 1
        if re.search(r'\bvoid\s+Start\s*\(', code) and re.search(r'\bvoid\s+Update\s*\(', code):
            score += 1
        elif re.search(r'\bvoid\s+Start\s*\(', code) or re.search(r'\bvoid\s+Update\s*\(', code):
            score += 0.5

        # Has class definitions
        max_score += 1
        classes = re.findall(r'\bclass\s+(\w+)', code)
        if len(classes) >= 2:
            score += 1
        elif len(classes) == 1:
            score += 0.5

        # Has proper indentation
        max_score += 1
        lines = code.splitlines()
        indented = [ln for ln in lines if ln.startswith('    ') or ln.startswith('\t')]
        if len(indented) > len(lines) * 0.3:
            score += 1

        # Has comments
        max_score += 1
        if re.search(r'//|/\*', code):
            score += 0.5
        if re.search(r'///|/\*\*', code):
            score += 0.5

        # Has SerializeField or public fields
        max_score += 1
        if re.search(r'\[SerializeField\]|\bpublic\s+\w+\s+\w+\s*;', code):
            score += 1

        # Proper bracket matching
        max_score += 1
        open_b = code.count('{')
        close_b = code.count('}')
        if open_b > 0 and abs(open_b - close_b) <= 2:
            score += 1

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _assess_unity_complexity(code: str) -> float:
        """Assess Unity code complexity (0.0 - 1.0)."""
        score = 0.0
        max_score = 10.0

        classes = len(re.findall(r'\bclass\s+\w+', code))
        score += min(classes / 5.0, 2.0)

        methods = len(re.findall(
            r'\b(?:void|int|float|string|bool|IEnumerator|GameObject|Transform)\s+\w+\s*\(',
            code
        ))
        score += min(methods / 8.0, 2.0)

        control = len(re.findall(r'\b(?:if|else|for|foreach|while|switch|case|try|catch)\b', code))
        score += min(control / 10.0, 2.0)

        # Nesting depth
        max_indent = 0
        for line in code.splitlines():
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                max_indent = max(max_indent, indent)
        score += min(max_indent / 20.0, 1.0)

        # Advanced patterns
        advanced = 0
        if re.search(r'\bCoroutine\b|\bStartCoroutine\b', code):
            advanced += 1
        if re.search(r'\bLinq\b|\bSelect\b|\bWhere\b', code):
            advanced += 1
        if re.search(r'\bevent\s+|\bdelegate\b|\bAction\b', code):
            advanced += 1
        if re.search(r'\babstract\s+class\b|\binterface\s+', code):
            advanced += 1
        if re.search(r'\bGeneric\b|\b<T>\b', code):
            advanced += 1
        score += min(advanced / 3.0, 2.0)

        loc = len([ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith('//')])
        score += min(loc / 200.0, 1.0)

        return min(score / max_score, 1.0)

    @staticmethod
    def _assess_unity_completeness(code: str, result: GameAnalysisResult) -> float:
        """Assess how complete the Unity game is (0.0 - 1.0)."""
        score = 0.0
        max_score = 0.0

        # Has MonoBehaviour
        max_score += 1
        if re.search(r':\s*MonoBehaviour\b', code):
            score += 1

        # Has player input
        max_score += 1
        if result.components_used.get("input"):
            score += 1

        # Has physics / collision
        max_score += 1
        if result.components_used.get("physics"):
            score += 1

        # Has game logic (score, health, timer)
        max_score += 1
        game_logic = 0
        if re.search(r'\bscore\b', code, re.IGNORECASE):
            game_logic += 1
        if re.search(r'\bhealth\b|\bhp\b|\bdamage\b', code, re.IGNORECASE):
            game_logic += 1
        if re.search(r'\btimer\b|\bcountdown\b', code, re.IGNORECASE):
            game_logic += 1
        score += min(game_logic / 2.0, 1.0)

        # Has spawn/destroy
        max_score += 1
        if re.search(r'\bInstantiate\b', code) or re.search(r'\bDestroy\b', code):
            score += 1

        # Has UI elements
        max_score += 1
        if result.components_used.get("ui"):
            score += 1

        # Has audio
        max_score += 1
        if result.components_used.get("audio"):
            score += 1
        elif "audio" in result.game_features:
            score += 0.5

        # Has scene/level management
        max_score += 1
        if "scene_management" in result.game_features:
            score += 1

        # Has multiple scripts/classes
        max_score += 1
        classes = len(re.findall(r'\bclass\s+\w+', code))
        if classes >= 3:
            score += 1
        elif classes >= 2:
            score += 0.5

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _check_unity_quality(code: str) -> List[str]:
        """Check Unity code quality."""
        notes = []
        if re.search(r'///|/\*\*', code):
            notes.append("✅ يحتوي على توثيق (XML documentation)")
        if re.search(r'\[SerializeField\]', code):
            notes.append("✅ يستخدم [SerializeField] بدلاً من public fields (أفضل ممارسة)")
        if re.search(r'\bprivate\s+', code):
            notes.append("✅ يستخدم التغليف (private members)")
        if re.search(r'\btry\s*\{.*\bcatch\b', code, re.DOTALL):
            notes.append("✅ يحتوي على معالجة أخطاء")
        if re.search(r'\bconst\s+|\breadonly\s+', code):
            notes.append("✅ يستخدم const/readonly للثوابت")
        if re.search(r'#region\b', code):
            notes.append("✅ يستخدم regions لتنظيم الكود")

        if not re.search(r'//|/\*', code):
            notes.append("⚠️ لا يحتوي على تعليقات — يُنصح بإضافة تعليقات توضيحية")
        if re.search(r'\bpublic\s+\w+\s+\w+\s*;', code) and not re.search(r'\[SerializeField\]', code):
            notes.append("⚠️ يستخدم public fields بدلاً من [SerializeField] — يُفضل التغليف")
        if re.search(r'\bFind\s*\(\s*"', code):
            notes.append("⚠️ يستخدم GameObject.Find() — بطيء، يُفضل استخدام references")
        if re.search(r'\bGetComponent\b.*\bUpdate\b', code, re.DOTALL):
            notes.append("💡 يُفضل تخزين نتيجة GetComponent في Start() بدلاً من Update()")

        return notes

    @staticmethod
    def _detect_csharp_syntax_issues(code: str) -> List[str]:
        """Detect potential syntax issues in C# code."""
        errors = []
        if code.count('{') != code.count('}'):
            diff = code.count('{') - code.count('}')
            if diff > 0:
                errors.append(f"❌ أقواس غير متطابقة: {diff} قوس '{{' بدون إغلاق")
            else:
                errors.append(f"❌ أقواس غير متطابقة: {abs(diff)} قوس '}}' زائد")
        if code.count('(') != code.count(')'):
            errors.append("❌ أقواس دائرية غير متطابقة")

        class_names = re.findall(r'\bclass\s+(\w+)', code)
        seen = set()
        for name in class_names:
            if name in seen:
                errors.append(f"❌ اسم الـ class مكرر: {name}")
            seen.add(name)

        return errors

    @staticmethod
    def _detect_unity_warnings(code: str) -> List[str]:
        """Detect Unity-specific warnings."""
        warnings = []
        if re.search(r'\bFind\s*\(\s*"', code):
            warnings.append("⚠️ استخدام Find() غير فعال — يُفضل استخدام references مباشرة")
        if re.search(r'\bSendMessage\s*\(', code):
            warnings.append("⚠️ استخدام SendMessage() بطيء — يُفضل استخدام interfaces أو events")
        if re.search(r'\bnew\s+\w+\[.*\]', code) and re.search(r'\bUpdate\b', code):
            warnings.append("⚠️ إنشاء مصفوفات في Update() يسبب ضغطاً على GC")
        if re.search(r'catch\s*\(\w*\)\s*\{\s*\}', code):
            warnings.append("⚠️ كتلة catch فارغة — يجب معالجة الخطأ")
        # Check for very long Update methods
        in_update = False
        update_lines = 0
        for line in code.splitlines():
            if re.search(r'\bvoid\s+Update\s*\(', line):
                in_update = True
                update_lines = 0
            if in_update:
                update_lines += 1
                if update_lines > 60:
                    warnings.append("⚠️ دالة Update() طويلة جداً — يُفضل تقسيمها")
                    in_update = False
            if in_update and line.strip() == '}' and update_lines > 2:
                in_update = False
        return warnings

    @staticmethod
    def _try_execute_unity(code: str) -> Optional[Dict[str, Any]]:
        """Try to compile/check Unity code if dotnet SDK is available."""
        dotnet_path = shutil.which("dotnet")
        if not dotnet_path:
            return None

        result: Dict[str, Any] = {"sdk_available": True, "dotnet_path": dotnet_path}
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="btec_unity_")
            cs_file = os.path.join(tmp_dir, "PlayerScript.cs")
            with open(cs_file, "w", encoding="utf-8") as f:
                f.write(code)

            # Just check syntax with dotnet-script or csc
            # We can't fully compile Unity code without Unity assemblies,
            # but we can check basic C# syntax
            proc = subprocess.run(
                [dotnet_path, "script", cs_file, "--", "--check"],
                capture_output=True, text=True, timeout=30, cwd=tmp_dir,
            )
            result["analysis"] = {
                "passed": proc.returncode == 0,
                "stdout": proc.stdout[:2000],
                "stderr": proc.stderr[:2000],
            }
        except FileNotFoundError:
            result["analysis"] = {"skipped": True, "reason": "dotnet-script not available"}
        except subprocess.TimeoutExpired:
            result["analysis"] = {"passed": False, "error": "Compilation timed out"}
        except Exception as e:
            result["analysis"] = {"passed": False, "error": str(e)}
        finally:
            if tmp_dir and os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
        return result

    # ═══════════════════════════════════════════════════
    # GAMEMAKER GML Methods
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _extract_gamemaker_blocks(text: str) -> List[GameCodeBlock]:
        """Extract GameMaker GML code blocks from text."""
        blocks: List[GameCodeBlock] = []

        if GameCodeAnalyzer._is_mostly_code(text) and GameCodeAnalyzer._is_gamemaker_code(text):
            return [GameCodeBlock(text.strip(), "gamemaker", "full_text")]

        # Markdown fences
        fence_pattern = re.compile(
            r'```(?:gml|gamemaker)?\s*\n(.*?)```',
            re.DOTALL | re.IGNORECASE,
        )
        for match in fence_pattern.finditer(text):
            code = match.group(1).strip()
            if code and GameCodeAnalyzer._is_gamemaker_code(code):
                blocks.append(GameCodeBlock(code, "gamemaker", "markdown_fence"))

        remaining = fence_pattern.sub('', text)

        # GML event blocks: /// @desc or // Create Event etc
        event_pattern = re.compile(
            r'((?:///?\s*@?\w+.*?\n)(?:.*?\n)*?(?=///?\s*@?\w+|\Z))',
            re.MULTILINE,
        )
        for match in event_pattern.finditer(remaining):
            code = match.group(0).strip()
            if len(code) > 40 and GameCodeAnalyzer._is_gamemaker_code(code):
                if not any(code[:50] in b.code for b in blocks):
                    blocks.append(GameCodeBlock(code, "gamemaker", "event_block"))

        # Inline detection
        _CODE_LINE = (
            r'[ \t]*(?:var\s|if\s*\(|for\s*\(|while\s*\(|'
            r'draw_|instance_|place_|keyboard_|mouse_|room_|game_|'
            r'audio_|sprite_|image_|alarm\[|global\.|'
            r'}\s*$|{\s*$|//|speed\s*=|direction\s*=|'
            r'\w+\s*=\s*|scr_|obj_|spr_|rm_)'
        )
        code_region_pattern = re.compile(
            r'((?:^' + _CODE_LINE + r'.*$\n?(?:\s*\n){0,2}){3,})',
            re.MULTILINE,
        )
        for match in code_region_pattern.finditer(remaining):
            code = match.group(0).strip()
            if len(code) > 40 and GameCodeAnalyzer._is_gamemaker_code(code):
                if not any(code[:50] in b.code for b in blocks):
                    blocks.append(GameCodeBlock(code, "gamemaker", "inline_detected"))

        if not blocks and len(remaining.strip()) > 40:
            if GameCodeAnalyzer._is_gamemaker_code(remaining):
                blocks.append(GameCodeBlock(remaining.strip(), "gamemaker", "full_text"))

        return blocks

    @staticmethod
    def _is_gamemaker_code(text: str) -> bool:
        """Check if text looks like GameMaker GML code."""
        score = 0
        for pattern in _GAMEMAKER_INDICATORS:
            if re.search(pattern, text):
                score += 1
        return score >= 3

    @staticmethod
    def _detect_gamemaker_components(code: str) -> Dict[str, List[str]]:
        """Detect GameMaker components used, categorized."""
        found: Dict[str, List[str]] = {}
        for category, items in _GAMEMAKER_CATEGORIES.items():
            hits = []
            for item in items:
                if re.search(r'\b' + re.escape(item) + r'\b', code):
                    hits.append(item)
            if hits:
                found[category] = hits
        return found

    @staticmethod
    def _detect_gamemaker_features(code: str) -> List[str]:
        """Detect GameMaker-specific features used."""
        features = []
        feature_patterns = {
            "movement": r'\bspeed\b|\bdirection\b|\bhspeed\b|\bvspeed\b|\bmove_towards\b',
            "collision": r'\bplace_meeting\b|\bcollision_\w+\b|\bposition_meeting\b',
            "drawing": r'\bdraw_\w+\b',
            "input_keyboard": r'\bkeyboard_check\b|\bvk_\w+\b',
            "input_mouse": r'\bmouse_check\b|\bmouse_[xy]\b',
            "audio": r'\baudio_play_sound\b|\baudio_stop\b',
            "sprites_animation": r'\bsprite_index\b|\bimage_speed\b|\bimage_index\b',
            "room_management": r'\broom_goto\b|\broom_restart\b',
            "data_structures": r'\bds_list_\w+\b|\bds_map_\w+\b|\bds_grid_\w+\b',
            "surfaces": r'\bsurface_\w+\b',
            "alarms": r'\balarm\[\d+\]',
            "particles": r'\bpart_\w+\b',
            "paths": r'\bpath_\w+\b',
            "scripts": r'\bscr_\w+\b',
            "global_variables": r'\bglobal\.\w+\b',
            "instance_management": r'\binstance_create\b|\binstance_destroy\b|\binstance_exists\b',
            "score_system": r'\bscore\b|\bglobal\.score\b',
            "lives_system": r'\blives\b|\bglobal\.lives\b|\bglobal\.health\b',
            "state_machine": r'\bstate\b|\bswitch\s*\(\s*state\b',
        }
        for feature, pattern in feature_patterns.items():
            if re.search(pattern, code, re.IGNORECASE):
                features.append(feature)
        return features

    @staticmethod
    def _assess_gamemaker_structure(code: str, blocks: List[GameCodeBlock]) -> float:
        """Assess GameMaker code structure quality."""
        score = 0.0
        max_score = 0.0

        # Has comments
        max_score += 1
        if re.search(r'//|/\*|///\s*@', code):
            score += 1

        # Has event organization (comments like // Create Event, // Step Event)
        max_score += 1
        if re.search(r'//\s*(?:Create|Step|Draw|Alarm|Collision|Destroy)\s*Event', code, re.IGNORECASE):
            score += 1
        elif re.search(r'///\s*@desc', code):
            score += 0.5

        # Uses variables properly
        max_score += 1
        if re.search(r'\bvar\s+\w+\s*=', code):
            score += 1

        # Has multiple code blocks / events
        max_score += 1
        if len(blocks) >= 3:
            score += 1
        elif len(blocks) >= 2:
            score += 0.5

        # Uses functions / scripts
        max_score += 1
        if re.search(r'\bfunction\s+\w+\b|\bscr_\w+\b', code):
            score += 1

        # Proper bracket matching
        max_score += 1
        if code.count('{') > 0 and abs(code.count('{') - code.count('}')) <= 2:
            score += 1

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _assess_gamemaker_complexity(code: str) -> float:
        """Assess GameMaker code complexity."""
        score = 0.0
        max_score = 10.0

        functions = len(re.findall(r'\bfunction\s+\w+|scr_\w+', code))
        score += min(functions / 5.0, 2.0)

        control = len(re.findall(r'\b(?:if|else|for|while|switch|case|repeat|do)\b', code))
        score += min(control / 10.0, 2.0)

        unique_functions = len(set(re.findall(r'\b(?:draw_|instance_|place_|audio_|ds_|surface_|part_)\w+', code)))
        score += min(unique_functions / 10.0, 2.0)

        max_indent = 0
        for line in code.splitlines():
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                max_indent = max(max_indent, indent)
        score += min(max_indent / 16.0, 1.0)

        advanced = 0
        if re.search(r'\bds_\w+\b', code):
            advanced += 1
        if re.search(r'\bsurface_\w+\b', code):
            advanced += 1
        if re.search(r'\bshader_\w+\b', code):
            advanced += 1
        if re.search(r'\bstate\b.*\bswitch\b', code, re.DOTALL):
            advanced += 1
        score += min(advanced / 2.0, 2.0)

        loc = len([ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith('//')])
        score += min(loc / 150.0, 1.0)

        return min(score / max_score, 1.0)

    @staticmethod
    def _assess_gamemaker_completeness(code: str, result: GameAnalysisResult) -> float:
        """Assess GameMaker game completeness."""
        score = 0.0
        max_score = 0.0

        max_score += 1
        if result.components_used.get("movement"):
            score += 1

        max_score += 1
        if result.components_used.get("input"):
            score += 1

        max_score += 1
        if result.components_used.get("collision"):
            score += 1

        max_score += 1
        if result.components_used.get("drawing"):
            score += 1

        max_score += 1
        if result.components_used.get("instances"):
            score += 1

        max_score += 1
        if result.components_used.get("audio"):
            score += 1

        max_score += 1
        if result.components_used.get("rooms"):
            score += 1

        max_score += 1
        if re.search(r'\bscore\b|\bglobal\.score\b', code, re.IGNORECASE):
            score += 1

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _check_gamemaker_quality(code: str) -> List[str]:
        """Check GameMaker code quality."""
        notes = []
        if re.search(r'///\s*@desc', code):
            notes.append("✅ يستخدم JSDoc-style documentation")
        if re.search(r'\bfunction\s+\w+', code):
            notes.append("✅ يستخدم دوال مخصصة لتنظيم الكود")
        if re.search(r'\benum\s+\w+', code):
            notes.append("✅ يستخدم enums للثوابت")
        if re.search(r'\bvar\s+_\w+', code):
            notes.append("✅ يستخدم naming conventions للمتغيرات المحلية")

        if not re.search(r'//|/\*', code):
            notes.append("⚠️ لا يحتوي على تعليقات")
        if re.search(r'\bglobal\.\w+', code) and len(re.findall(r'\bglobal\.\w+', code)) > 10:
            notes.append("⚠️ استخدام مفرط للمتغيرات العامة (global) — يُفضل تنظيمها")
        return notes

    @staticmethod
    def _detect_gml_syntax_issues(code: str) -> List[str]:
        """Detect GML syntax issues."""
        errors = []
        if code.count('{') != code.count('}'):
            diff = code.count('{') - code.count('}')
            if diff > 0:
                errors.append(f"❌ أقواس غير متطابقة: {diff} قوس بدون إغلاق")
            else:
                errors.append(f"❌ أقواس غير متطابقة: {abs(diff)} قوس زائد")
        if code.count('(') != code.count(')'):
            errors.append("❌ أقواس دائرية غير متطابقة")
        return errors

    @staticmethod
    def _detect_gamemaker_warnings(code: str) -> List[str]:
        """Detect GameMaker warnings."""
        warnings = []
        if re.search(r'\bshow_message\b', code):
            warnings.append("⚠️ استخدام show_message() يوقف اللعبة — يُفضل draw_text()")
        if re.search(r'\bgame_end\b', code) and not re.search(r'\bif\b.*\bgame_end\b', code, re.DOTALL):
            warnings.append("⚠️ game_end() بدون شرط — قد ينهي اللعبة فوراً")
        return warnings

    # ═══════════════════════════════════════════════════
    # GODOT / GDScript Methods
    # ═══════════════════════════════════════════════════

    _GODOT_ENGINE_CATEGORIES = {
        "nodes": ["CharacterBody2D", "RigidBody2D", "Area2D", "StaticBody2D", "Node2D", "Control", "CanvasLayer"],
        "physics": ["move_and_slide", "move_and_collide", "CollisionShape2D", "CollisionPolygon2D"],
        "input": ["Input.is_action_pressed", "Input.get_axis", "Input.get_vector"],
        "ui": ["Button", "Label", "VBoxContainer", "HBoxContainer", "TextureRect"],
        "animation": ["AnimationPlayer", "AnimatedSprite2D", "Tween"],
        "tilemap": ["TileMap", "TileMapLayer"],
        "scene": ["get_tree()", "change_scene_to_file"],
    }

    @staticmethod
    def _extract_godot_blocks(text: str) -> List[GameCodeBlock]:
        blocks: List[GameCodeBlock] = []
        fence_pattern = re.compile(
            r'```(?:gdscript|gd)?\s*\n(.*?)```',
            re.DOTALL | re.IGNORECASE,
        )
        for match in fence_pattern.finditer(text):
            code = match.group(1).strip()
            if code and GameCodeAnalyzer._is_godot_code(code):
                blocks.append(GameCodeBlock(code, "godot", "markdown_fence"))

        remaining = fence_pattern.sub('', text)
        gd_region = re.compile(
            r'((?:^[\t ]*(?:extends|class_name|signal|func|var|const|enum)\b.*\n(?:.*\n){0,200}){1,})',
            re.MULTILINE,
        )
        for match in gd_region.finditer(remaining):
            code = match.group(0).strip()
            if len(code) > 50 and GameCodeAnalyzer._is_godot_code(code):
                if not any(code[:80] in b.code for b in blocks):
                    blocks.append(GameCodeBlock(code, "godot", "region"))

        looks_godot = GameCodeAnalyzer._is_godot_code(text)
        looks_code = GameCodeAnalyzer._is_mostly_code(text) or bool(
            re.search(r'\bfunc\s+\w+', text) and re.search(r'\bextends\s+\w+', text)
        )
        if not blocks and len(text.strip()) > 50 and looks_godot and looks_code:
            blocks.append(GameCodeBlock(text.strip(), "godot", "full_text"))

        return blocks

    @staticmethod
    def _is_godot_code(text: str) -> bool:
        score = 0
        for pattern in _GODOT_INDICATORS:
            if re.search(pattern, text):
                score += 1
        return score >= 3

    @staticmethod
    def _detect_godot_components(code: str) -> Dict[str, List[str]]:
        found: Dict[str, List[str]] = {}
        for category, items in GameCodeAnalyzer._GODOT_ENGINE_CATEGORIES.items():
            hits = []
            for item in items:
                if item.endswith("()"):
                    needle = item
                elif "(" in item:
                    needle = re.escape(item)
                else:
                    needle = r'\b' + re.escape(item) + r'\b'
                if re.search(needle, code):
                    hits.append(item)
            if hits:
                found[category] = hits
        return found

    @staticmethod
    def _detect_godot_features(code: str) -> List[str]:
        features: List[str] = []
        if re.search(r'\bAnimatedSprite\d?\b|\bSprite2D\b', code):
            features.append("sprite_rendering")
        if re.search(r'\bAudioStreamPlayer\d?\b|\bAudioStream\b', code):
            features.append("audio_stream")
        if re.search(r'\bAnimationPlayer\b|\bTween\b', code):
            features.append("animation")
        if re.search(r'\bTileMap(?:Layer)?\b', code):
            features.append("tilemap")
        if re.search(r'\bParallax(?:Layer|Background)\b|\bCamera2D\b', code):
            features.append("camera_parallax")
        if re.search(r'\bRigidBody\b|\bPhysicsDirectBodyState\b', code):
            features.append("rigid_body")
        return features

    @staticmethod
    def _assess_godot_structure(code: str, blocks: List[GameCodeBlock]) -> float:
        score = 0.0
        max_score = 0.0
        max_score += 1
        if re.search(r'#|"""', code):
            score += 1
        max_score += 1
        if re.search(r'\bextends\s+\w+', code):
            score += 1
        max_score += 1
        func_n = len(re.findall(r'\bfunc\s+\w+', code))
        if func_n >= 3:
            score += 1
        elif func_n >= 1:
            score += 0.6
        max_score += 1
        if len(blocks) >= 2:
            score += 1
        elif len(blocks) == 1:
            score += 0.5
        max_score += 1
        if code.count('{') > 0 and abs(code.count('{') - code.count('}')) <= 2:
            score += 0.8
        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _assess_godot_complexity(code: str) -> float:
        score = 0.0
        max_score = 10.0
        score += min(len(re.findall(r'\bfunc\s+\w+', code)) / 6.0, 2.0)
        score += min(len(re.findall(r'\b(?:if|elif|else|for|while|match)\b', code)) / 12.0, 2.5)
        score += min(len(re.findall(r'\bsignal\b', code)) / 3.0, 1.0)
        score += min(len(re.findall(r'\bawait\b', code)) / 6.0, 1.5)
        score += min(len([ln for ln in code.splitlines() if ln.strip() and not ln.strip().startswith('#')]) / 200.0, 3.0)
        return min(score / max_score, 1.0)

    @staticmethod
    def _assess_godot_completeness(code: str, result: GameAnalysisResult) -> float:
        score = 0.0
        max_score = 0.0
        comps = result.components_used
        max_score += 1
        if comps.get("nodes"):
            score += 1
        max_score += 1
        if comps.get("input"):
            score += 1
        max_score += 1
        if comps.get("physics"):
            score += 1
        max_score += 1
        if comps.get("scene"):
            score += 1
        max_score += 1
        if result.game_features:
            score += min(len(result.game_features) / 4.0, 1.0)
        max_score += 1
        if re.search(r'\b(area|body)_(entered|exited)', code):
            score += 0.5
        max_score += 0.5
        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _check_godot_quality(code: str) -> List[str]:
        notes: List[str] = []
        if re.search(r'"""[\s\S]+?"""|##', code):
            notes.append("✅ وجود توثيق/تعليقات في GDScript")
        if re.search(r'\bsignal\b', code):
            notes.append("✅ استخدام الإشارات (signals)")
        if re.search(r'\b@onready\b', code):
            notes.append("✅ استخدام @onready لتنظيم المراجع")
        if not re.search(r'\bfunc\s+_(?:ready|process|physics_process)\b', code):
            notes.append("⚠️ لم يتم رصد دوال دورة حياة واضحة (_ready / _process / _physics_process)")
        return notes

    @staticmethod
    def _detect_godot_warnings(code: str) -> List[str]:
        warnings: List[str] = []
        if re.search(r'\bget_node\s*\(\s*["\']%', code):
            warnings.append("⚠️ مسارات عقد صارمة مع get_node — صعبة الصيانة عند إعادة تسمية العقد")
        return warnings

    # ═══════════════════════════════════════════════════
    # SCRATCH Methods
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _categorize_scratch_blocks(all_blocks: Dict[str, Any]) -> Dict[str, List[str]]:
        """Categorize Scratch blocks by type."""
        found: Dict[str, set] = {}
        for _block_id, block in all_blocks.items():
            if not isinstance(block, dict):
                continue
            opcode = block.get("opcode", "")
            for category, opcodes in _SCRATCH_CATEGORIES.items():
                if opcode in opcodes:
                    found.setdefault(category, set()).add(opcode)
        return {k: sorted(v) for k, v in found.items()}

    @staticmethod
    def _detect_scratch_features(all_blocks: Dict[str, Any], targets: list) -> List[str]:
        """Detect game features in Scratch project."""
        features = []
        opcodes = {b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)}

        if opcodes & {"motion_movesteps", "motion_gotoxy", "motion_changexby", "motion_changeyby"}:
            features.append("movement")
        if opcodes & {"sensing_keypressed", "event_whenkeypressed"}:
            features.append("keyboard_input")
        if opcodes & {"sensing_mousedown", "event_whenthisspriteclicked", "sensing_mousex"}:
            features.append("mouse_input")
        if opcodes & {"sensing_touchingobject", "sensing_touchingcolor"}:
            features.append("collision_detection")
        if opcodes & {"sound_play", "sound_playuntildone"}:
            features.append("audio")
        if opcodes & {"looks_switchcostumeto", "looks_nextcostume"}:
            features.append("costume_animation")
        if opcodes & {"data_setvariableto", "data_changevariableby"}:
            features.append("variables_scoring")
        if opcodes & {"control_create_clone_of", "control_delete_this_clone"}:
            features.append("cloning")
        if opcodes & {"event_broadcast", "event_broadcastandwait"}:
            features.append("messaging")
        if opcodes & {"procedures_definition", "procedures_call"}:
            features.append("custom_blocks")
        if opcodes & {"control_forever", "control_repeat", "control_repeat_until"}:
            features.append("loops")
        if opcodes & {"control_if", "control_if_else"}:
            features.append("conditionals")
        if opcodes & {"operator_random"}:
            features.append("randomness")
        if opcodes & {"looks_switchbackdropto"}:
            features.append("backdrop_switching")
        if opcodes & {"sensing_timer"}:
            features.append("timer")
        if opcodes & {"data_addtolist", "data_deleteoflist"}:
            features.append("lists")

        # Multi-sprite interaction
        if len([t for t in targets if not t.get("isStage")]) > 1:
            features.append("multi_sprite")

        return features

    @staticmethod
    def _assess_scratch_structure(project_info: Dict, all_blocks: Dict, targets: list) -> float:
        """Assess Scratch project structure."""
        score = 0.0
        max_score = 0.0

        # Has multiple sprites
        max_score += 1
        sc = project_info.get("sprite_count", 0)
        if sc >= 3:
            score += 1
        elif sc >= 1:
            score += 0.5

        # Has costumes (visual design effort)
        max_score += 1
        tc = project_info.get("total_costumes", 0)
        if tc >= 5:
            score += 1
        elif tc >= 2:
            score += 0.5

        # Has sounds
        max_score += 1
        ts = project_info.get("total_sounds", 0)
        if ts >= 2:
            score += 1
        elif ts >= 1:
            score += 0.5

        # Has meaningful number of blocks
        max_score += 1
        tb = project_info.get("total_blocks", 0)
        if tb >= 50:
            score += 1
        elif tb >= 20:
            score += 0.5

        # Has custom blocks (functions)
        max_score += 1
        opcodes = {b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)}
        if "procedures_definition" in opcodes:
            score += 1

        # Uses variables
        max_score += 1
        if project_info.get("variables", 0) > 0:
            score += 1

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _assess_scratch_complexity(all_blocks: Dict, targets: list) -> float:
        """Assess Scratch project complexity."""
        score = 0.0
        max_score = 10.0

        opcodes = [b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)]
        unique_opcodes = set(opcodes)

        # Variety of block types
        score += min(len(unique_opcodes) / 20.0, 2.0)

        # Number of scripts (top-level hat blocks)
        hat_blocks = [op for op in opcodes if op.startswith("event_")]
        score += min(len(hat_blocks) / 8.0, 2.0)

        # Control flow complexity
        control_blocks = [op for op in opcodes if op.startswith("control_")]
        score += min(len(control_blocks) / 10.0, 2.0)

        # Uses operators
        operator_blocks = [op for op in opcodes if op.startswith("operator_")]
        score += min(len(operator_blocks) / 5.0, 1.0)

        # Uses custom blocks
        if "procedures_definition" in unique_opcodes:
            score += 1.0

        # Multi-sprite with messaging
        if "event_broadcast" in unique_opcodes and len(targets) > 2:
            score += 1.0

        # Total blocks
        score += min(len(opcodes) / 100.0, 1.0)

        return min(score / max_score, 1.0)

    @staticmethod
    def _assess_scratch_completeness(project_info: Dict, all_blocks: Dict, result: GameAnalysisResult) -> float:
        """Assess Scratch game completeness."""
        score = 0.0
        max_score = 0.0

        feats = set(result.game_features)

        max_score += 1
        if "movement" in feats:
            score += 1

        max_score += 1
        if "keyboard_input" in feats or "mouse_input" in feats:
            score += 1

        max_score += 1
        if "collision_detection" in feats:
            score += 1

        max_score += 1
        if "variables_scoring" in feats:
            score += 1

        max_score += 1
        if "audio" in feats:
            score += 1

        max_score += 1
        if "costume_animation" in feats or "backdrop_switching" in feats:
            score += 1

        max_score += 1
        if "loops" in feats and "conditionals" in feats:
            score += 1

        max_score += 1
        if "multi_sprite" in feats:
            score += 1

        return score / max_score if max_score > 0 else 0.0

    @staticmethod
    def _detect_gameplay_elements_scratch(all_blocks: Dict, targets: list) -> Dict[str, Any]:
        """Detect gameplay elements in Scratch project."""
        opcodes = {b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)}
        elements: Dict[str, Any] = {}

        if opcodes & {"motion_movesteps", "motion_changexby", "motion_changeyby"}:
            elements["player_movement"] = True
        if "sensing_touchingobject" in opcodes:
            elements["collision"] = True
        if "data_changevariableby" in opcodes:
            elements["score_tracking"] = True
        if "control_create_clone_of" in opcodes:
            elements["enemy_spawning"] = True
        if opcodes & {"looks_say", "looks_sayforsecs"}:
            elements["dialog"] = True
        if "sensing_timer" in opcodes:
            elements["timer_mechanic"] = True
        if "looks_switchbackdropto" in opcodes:
            elements["level_transitions"] = True
        if "control_stop" in opcodes:
            elements["game_over"] = True

        return elements

    @staticmethod
    def _check_scratch_quality(project_info: Dict, all_blocks: Dict, targets: list) -> List[str]:
        """Check Scratch project quality."""
        notes = []
        opcodes = {b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)}

        if "procedures_definition" in opcodes:
            notes.append("✅ يستخدم كتل مخصصة (My Blocks) لتنظيم البرنامج")
        if project_info.get("sprite_count", 0) >= 3:
            notes.append("✅ مشروع يحتوي على شخصيات متعددة")
        if project_info.get("total_sounds", 0) >= 2:
            notes.append("✅ يحتوي على مؤثرات صوتية")
        if project_info.get("total_costumes", 0) >= 5:
            notes.append("✅ يحتوي على رسومات/أزياء متعددة")
        if "event_broadcast" in opcodes:
            notes.append("✅ يستخدم الرسائل (Broadcast) للتواصل بين الشخصيات")

        if project_info.get("sprite_count", 0) == 0:
            notes.append("⚠️ لا يحتوي على شخصيات (Sprites)")
        if project_info.get("total_blocks", 0) < 20:
            notes.append("⚠️ عدد الكتل قليل جداً — المشروع قد يكون غير مكتمل")
        if project_info.get("variables", 0) == 0 and project_info.get("total_blocks", 0) > 20:
            notes.append("💡 لا يستخدم متغيرات — يمكن إضافة نظام نقاط أو حياة")

        return notes

    @staticmethod
    def _detect_scratch_warnings(project_info: Dict, all_blocks: Dict) -> List[str]:
        """Detect potential issues in Scratch project."""
        warnings = []
        if project_info.get("total_blocks", 0) > 500:
            warnings.append("⚠️ مشروع كبير جداً — قد يكون بطيئاً عند التشغيل")

        # Check for forever loops without waits
        opcodes_list = [b.get("opcode", "") for b in all_blocks.values() if isinstance(b, dict)]
        forever_count = opcodes_list.count("control_forever")
        wait_count = opcodes_list.count("control_wait")
        if forever_count > 0 and wait_count == 0:
            warnings.append("⚠️ حلقات forever بدون wait — قد يسبب تجمّد البرنامج")

        return warnings

    # ═══════════════════════════════════════════════════
    # Common Gameplay Detection
    # ═══════════════════════════════════════════════════

    @staticmethod
    def _detect_gameplay_elements(code: str, engine: str) -> Dict[str, Any]:
        """Detect common gameplay elements in code (Unity/GameMaker/Godot)."""
        elements: Dict[str, Any] = {}

        # Player movement
        if re.search(
            r'\bInput\.(?:Get(?:Key|Axis|Vector)|is_action_pressed|get_axis|get_vector)\b|'
            r'\bkeyboard_check\b|\bmove_and_slide\b|\bvelocity\b',
            code,
        ):
            elements["player_movement"] = True

        # Collision/physics
        if re.search(
            r'\bOnCollision\w+\b|\bOnTrigger\w+\b|\bplace_meeting\b|'
            r'\b(area|body)_(entered|exited)\b|\bcollision_|move_and_collide\b',
            code,
            re.IGNORECASE,
        ):
            elements["collision"] = True

        # Score system
        if re.search(r'\bscore\b|\bScore\b|\bpoints\b', code, re.IGNORECASE):
            elements["score_tracking"] = True

        # Health/lives
        if re.search(r'\bhealth\b|\bHP\b|\blives\b|\bdamage\b', code, re.IGNORECASE):
            elements["health_system"] = True

        # Enemy/NPC
        if re.search(r'\benemy\b|\bEnemy\b|\bNPC\b|\bAI\b', code, re.IGNORECASE):
            elements["enemies"] = True

        # Spawning
        if re.search(r'\bInstantiate\b|\binstance_create\b|\bdup(?:licate)?\(\)\b|\binstantiate\b', code):
            elements["spawning"] = True

        # Level/scene transitions
        if re.search(r'\bLoadScene\b|\broom_goto\b|change_scene|get_tree\(\)\.change_scene', code):
            elements["level_transitions"] = True

        # Game over / restart
        if re.search(r'\bgame\s*over\b|\brestart\b|\bgame_restart\b', code, re.IGNORECASE):
            elements["game_over"] = True

        # Timer/countdown
        if re.search(r'\btimer\b|\bcountdown\b|\bTime\.time\b', code, re.IGNORECASE):
            elements["timer_mechanic"] = True

        # Power-ups / collectibles
        if re.search(r'\bpower.?up\b|\bcollect\b|\bpickup\b|\bcoin\b', code, re.IGNORECASE):
            elements["collectibles"] = True

        # Menu / UI
        if re.search(r'\bmenu\b|\bMenu\b|\bstart\s*screen\b|\bmain\s*menu\b', code, re.IGNORECASE):
            elements["menu_system"] = True

        # Save/load
        if re.search(r'\bPlayerPrefs\b|\bsave\b|\bload\b|\bini_\w+\b', code, re.IGNORECASE):
            elements["save_system"] = True

        return elements

    @staticmethod
    def _is_mostly_code(text: str) -> bool:
        """Check if text is primarily code."""
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) < 3:
            return False
        code_indicators = 0
        end_chars = {';', '{', '}', '(', ')', ','}
        start_words = ('using ', 'import ', '//', '@', 'class ', 'void ', 'public ',
                       'private ', 'var ', 'if ', 'for ', 'while ', 'return ',
                       'draw_', 'instance_', 'place_', 'function ',
                       'func ', 'extends ')
        for line in lines:
            stripped = line.strip()
            if stripped[-1:] in end_chars or any(stripped.startswith(w) for w in start_words):
                code_indicators += 1
        return code_indicators / len(lines) >= 0.4


# ═══════════════════════════════════════════════════════
# Convenience functions for external use
# ═══════════════════════════════════════════════════════

_SKIP_PATH_SEGMENT = frozenset({
    ".git", "node_modules", ".import", "library", "temp", "obj", "bin", ".vs",
    "build", "dist", "packages", "__pycache__", ".godot",
})

_CODE_EXT_FOR_DUAL = frozenset({
    ".gd", ".gml", ".cs", ".cpp", ".c", ".h", ".hpp", ".lua", ".js", ".ts", ".py", ".shader",
    ".hlsl", ".cginc",
})

_IMAGE_EXT_FOR_PLAGIARISM = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

_VIDEO_EXT_FOR_PLAGIARISM = frozenset(
    {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm", ".m4v", ".flv"}
)

_VERSION1_HINTS = (
    "/v1/", "\\v1\\", "_v1_", "-v1-", "ver1_", "_ver1", "/initial/", "\\initial\\",
    "prototype", "_proto", "/draft/", "\\draft\\", "_original", "\\first_ver", "/first_ver",
    "اولية", "الأولية", "الاولية", "نسخة1", "النسخة الاولى", "النسخة الأولى", "اولي_",
)

_VERSION2_HINTS = (
    "/v2/", "\\v2\\", "_v2_", "-v2-", "ver2_", "_ver2", "/final/", "\\final\\", "polish",
    "improved", "refined", "/improve/", "\\improve\\", "النهائية", "المحسنة", "محسنة",
    "نسخة2", "النسخة الثانية",
)


def _path_version_band(path_normalized: str) -> Optional[int]:
    """Return 1 (early), 2 (improved/final), or None if ambiguous."""
    s = path_normalized.replace("\\", "/").lower()
    s1 = sum(1 for m in _VERSION1_HINTS if m.lower() in s)
    s2 = sum(1 for m in _VERSION2_HINTS if m.lower() in s)
    if s2 > s1:
        return 2
    if s1 > s2:
        return 1
    return None


def _readable_code_paths(paths: List[str]) -> List[str]:
    """Filter disk paths down to plausible game-source files."""
    good: List[str] = []
    for raw in paths:
        p = Path(raw)
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        lower = str(p).lower()
        parts = Path(lower).parts
        if any(seg in _SKIP_PATH_SEGMENT or seg.endswith(".egg-info") for seg in parts):
            continue
        ext = p.suffix.lower()
        if ext == ".sb3":
            good.append(raw)
            continue
        if ext in _CODE_EXT_FOR_DUAL:
            good.append(raw)
    return sorted(set(good), key=lambda x: x.lower())


def _read_snippet(abs_path: str, soft_cap: int) -> str:
    try:
        return Path(abs_path).read_text(encoding="utf-8", errors="ignore")[:soft_cap]
    except OSError:
        return ""


def compact_source_for_ai_prompt(text: str, ext: str = "") -> str:
    """Trim blank lines and full-line comments — keeps executable logic for grading."""
    if not text or not text.strip():
        return text
    ext_l = (ext or "").lower()
    out: List[str] = []
    blank_run = 0
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.lstrip()
        if not s:
            blank_run += 1
            if blank_run <= 1:
                out.append("")
            continue
        blank_run = 0
        if ext_l in (".cs", ".cpp", ".c", ".h", ".hpp", ".js", ".ts", ".gd", ".gml", ".shader", ".hlsl", ".cginc"):
            if s.startswith("//"):
                continue
        elif ext_l == ".py" and s.startswith("#") and not s.startswith("#!"):
            continue
        out.append(line)
    compacted = "\n".join(out).strip()
    return compacted if compacted else text.strip()


def _readable_image_paths(paths: List[str]) -> List[str]:
    """Standalone screenshot/image files (not embedded in Word)."""
    good: List[str] = []
    for raw in paths:
        p = Path(raw)
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        lower = str(p).lower()
        parts = Path(lower).parts
        if any(seg in _SKIP_PATH_SEGMENT or seg.endswith(".egg-info") for seg in parts):
            continue
        if p.suffix.lower() in _IMAGE_EXT_FOR_PLAGIARISM:
            good.append(raw)
    return sorted(set(good), key=lambda x: x.lower())


def _ocr_image_snippet(abs_path: str, cap: int) -> str:
    try:
        from app.project_intelligence.ocr_runtime_extractor import _run_ocr_on_file, _try_import_ocr

        pytesseract, Image = _try_import_ocr()
        if not pytesseract:
            return ""
        raw, _err = _run_ocr_on_file(pytesseract, Image, Path(abs_path))
        return (raw or "").strip()[:cap]
    except Exception:
        return ""


def _video_ocr_snippets(paths: List[str], *, per_video_cap: int = 2500) -> List[str]:
    """Lightweight OCR on a few video keyframes for plagiarism corpus."""
    snippets: List[str] = []
    try:
        from app.project_intelligence.video_runtime_extractor import (
            extract_percentile_keyframes,
            list_submission_video_files,
        )
    except Exception:
        return snippets

    video_files = list_submission_video_files([Path(p) for p in paths])
    for vp in video_files[:2]:
        frames_dir = Path(tempfile.mkdtemp(prefix="plag_vid_"))
        try:
            frames, _meta = extract_percentile_keyframes(
                vp,
                frames_dir,
                percentiles=(0.0, 0.5, 1.0),
                max_duration_seconds=120.0,
            )
        except Exception:
            shutil.rmtree(frames_dir, ignore_errors=True)
            continue
        frame_texts: List[str] = []
        for fr in frames or []:
            fp = fr.get("frame_path")
            if not fp:
                continue
            ocr = _ocr_image_snippet(str(fp), 800)
            if ocr:
                frame_texts.append(ocr)
        shutil.rmtree(frames_dir, ignore_errors=True)
        if frame_texts:
            snippets.append(
                f"=== {vp.name} (video OCR) ===\n" + "\n".join(frame_texts)
            )
            if sum(len(s) for s in snippets) >= per_video_cap * 2:
                break
    return snippets


def _submission_files(paths: List[str]) -> List[Path]:
    """Explicit submission paths — no build-folder skip (used for plagiarism corpus)."""
    out: List[Path] = []
    for raw in paths:
        try:
            p = Path(raw)
            if p.is_file():
                out.append(p)
        except OSError:
            continue
    return out


def build_plagiarism_corpus(
    main_document_text: str,
    submission_paths: Optional[List[str]] = None,
    *,
    per_file_cap: int = 15_000,
    vision_analysis_text: str = "",
) -> str:
    """Student-owned text: Word + code + image OCR + video/vision — no grading prompts."""
    parts: List[str] = []
    if main_document_text and main_document_text.strip():
        parts.append(main_document_text.strip())

    path_list = list(submission_paths or [])
    for p in _submission_files(path_list):
        ext = p.suffix.lower()
        if ext in _CODE_EXT_FOR_DUAL and ext != ".sb3":
            body = _read_snippet(str(p), per_file_cap).strip()
            if body:
                parts.append(f"=== {p.name} (code) ===\n{body}")

    for p in _submission_files(path_list):
        if p.suffix.lower() not in _IMAGE_EXT_FOR_PLAGIARISM:
            continue
        ocr = _ocr_image_snippet(str(p), min(per_file_cap, 4000))
        if ocr:
            parts.append(f"=== {p.name} (image OCR) ===\n{ocr}")

    if vision_analysis_text and vision_analysis_text.strip():
        parts.append(
            "=== تحليل الصور/الفيديو (Vision) ===\n"
            + vision_analysis_text.strip()
        )

    parts.extend(_video_ocr_snippets(path_list))

    return "\n\n".join(parts)


def _build_godot_pck_grading_addon(submission_paths: List[str]) -> str:
    """GDScript/scene hints from Godot .pck when no loose .gd files were submitted."""
    try:
        from app.runtime_observation_sandbox import analyze_godot_pck
    except Exception:
        return ""

    lines: List[str] = []
    for raw in submission_paths or []:
        p = Path(raw)
        if p.suffix.lower() != ".pck" or not p.is_file():
            continue
        try:
            analysis = analyze_godot_pck(p)
        except OSError:
            continue
        if not analysis.get("valid"):
            continue
        sig = analysis.get("signals") or {}
        if not sig.get("has_gdscript") and not sig.get("has_scenes"):
            continue
        lines.append(
            f"--- Godot export pack: {p.name} ---\n"
            f"valid_pck=True gd_script_hits={sig.get('gd_script_hits', 0)} "
            f"scene_hits={sig.get('scene_hits', 0)} "
            f"has_audio={sig.get('has_audio_assets')} has_sprites={sig.get('has_sprite_assets')}\n"
            "(المصدر داخل .pck — لا ملفات .gd منفصلة في التسليم؛ يُقيَّم من التصدير والتوثيق.)"
        )
    if not lines:
        return ""
    header = (
        "═══════════════════════════════════════════\n"
        "[مرفق — تحليل تصدير Godot (.pck) — GDScript مضمّن في الحزمة]\n"
        "═══════════════════════════════════════════\n"
    )
    return header + "\n".join(lines) + "\n\n"


def build_dual_version_grading_addon(
    submission_paths: List[str],
    max_chars_per_side: int = 95_000,
    per_file_cap: int = 28_000,
    max_code_files: Optional[int] = None,
    *,
    compact: bool = False,
) -> str:
    """
    Arabic context block for batch grading when a student zipped both a write-up and code.

    Groups paths using heuristics (v1 vs v2, initial vs final, Arabic cues). Covers Unity
    (.cs), GameMaker (.gml), Godot (.gd), and Scratch (.sb3). Returns \"\" when nothing matches.
    """
    code_paths = _readable_code_paths(submission_paths)
    if max_code_files is not None and max_code_files > 0:
        gml_first = [p for p in code_paths if p.lower().endswith(".gml")]
        other = [p for p in code_paths if p not in gml_first]
        code_paths = (gml_first + other)[:max_code_files]
    if not code_paths:
        pck_addon = _build_godot_pck_grading_addon(submission_paths)
        return pck_addon

    v1_paths: List[str] = []
    v2_paths: List[str] = []
    neut_paths: List[str] = []
    for fp in code_paths:
        norm = fp.replace("\\", "/").lower()
        band = _path_version_band(norm)
        if band == 1:
            v1_paths.append(fp)
        elif band == 2:
            v2_paths.append(fp)
        else:
            neut_paths.append(fp)

    intro: List[str] = [
        "═══════════════════════════════════════════",
        "[مرفق تلقائي — تحليل كود مشروع اللعبة: نسخة أولى / محسّنة حيث يظهر ذلك من أسماء المجلدات]",
        "",
        "إن ظهر تمييز في مسارات الملفات (مثل v1 ومقابل v2، أو initial مقابل final، أو تمييز عربي مشابه)، "
        "يُقيَّم أيضًا **مدى التحسّن بين النُسختين** عندما تنطبق معايير التكرار أو المراجعة أو الاختبار. "
        "عبارات مثل «تم التنفيذ/الاختبار/التحسين» في الوورد لا تُعد دليلاً إلا إذا وافقتها لقطات أو نتائج اختبار أو ما يظهر هنا من كود. "
        "ما يلي ناتج آلية مساعدة؛ استمر اعتماد مستند الطالب الأساسي وما أرفق بحسب طلب المعايير.",
        "═══════════════════════════════════════════",
    ]

    def gather(paths: List[str], budget: int) -> Tuple[str, List[str]]:
        pieces: List[str] = []
        used = 0
        clipped: List[str] = []
        seen = set()
        for fp in sorted(paths, key=lambda x: x.lower()):
            try:
                key = os.path.normcase(os.path.abspath(fp))
            except OSError:
                key = fp
            if key in seen:
                continue
            seen.add(key)

            if used >= budget:
                break
            room = budget - used

            if fp.lower().endswith(".sb3"):
                d = analyze_scratch_project(fp)
                small = {
                    "file": fp,
                    "summary_ar": d.get("summary_ar"),
                    "engine": d.get("engine"),
                    "total_lines": d.get("total_lines"),
                    "scratch_project": d.get("scratch_project"),
                }
                piece = "--- Scratch (.sb3) ---\n" + json.dumps(small, ensure_ascii=False)
            else:
                body = _read_snippet(fp, per_file_cap)
                if not body.strip():
                    continue
                ext = Path(fp).suffix.lower()
                if compact:
                    body = compact_source_for_ai_prompt(body, ext)
                if not body.strip():
                    continue
                piece = f"--- {fp} ---\n{body.strip()}"

            if len(piece) > room:
                piece = piece[:room]
                clipped.append(fp)

            pieces.append(piece)
            used += len(piece)

            if len(piece) >= per_file_cap:
                clipped.append(fp)

            if used >= budget:
                break

        return ("\n\n".join(pieces), clipped)

    def section(title_ar: str, paths_list: List[str]) -> str:
        if not paths_list:
            return ""
        blob, clipped = gather(paths_list, max_chars_per_side)
        if not blob.strip():
            return ""
        analysis = analyze_game_code(blob)
        summ_ar = analysis.get("summary_ar") or ""
        info = json.dumps(
            {
                "engine": analysis.get("engine"),
                "code_blocks_count": analysis.get("code_blocks_count"),
                "structure_score": analysis.get("structure_score"),
                "complexity_score": analysis.get("complexity_score"),
                "completeness_score": analysis.get("completeness_score"),
            },
            ensure_ascii=False,
        )
        clip_note = "(تم اقتطاع بعض الملفات لمطابقة حد الطول الآلي للموديل)\n" if clipped else ""
        fenced = "```\n" + blob.strip()[: max_chars_per_side + 6000] + "\n```"
        return (
            f"\n### {title_ar}\nمسارات هذه الدُفعة: {len(paths_list)}\n{clip_note}"
            f"[تلخيص آلياً (عربي)]\n{summ_ar}\n"
            f"[مقاييس مختصرة]\n{info}\n"
            f"{fenced}\n"
        )

    sections: List[str] = []

    if v1_paths and v2_paths:
        sections.append(
            section("الطبقة الموسومة كنسخة أولى / تجريبية (v1 / initial وما شابه)", v1_paths)
        )
        sections.append(
            section("الطبقة الموسومة كنسخة محسّنة أو نهائية (v2 / final / improved)", v2_paths)
        )
        if neut_paths:
            sections.append(
                section(
                    "ملفات دون موسومة صريحة v1 أو v2 — ادْمجها ضمن قراءة المشروع ككل",
                    neut_paths,
                )
            )
    elif v1_paths:
        merged = list(dict.fromkeys(v1_paths + neut_paths))
        sections.append(section("مسارات تُصدَّف ضمن خانة النسخة المبكرة أو v1 (مع غير الموسوم)", merged))
    elif v2_paths:
        merged = list(dict.fromkeys(v2_paths + neut_paths))
        sections.append(section("مسارات تُصدَّف ضمن خانة المحسَّن أو v2 (مع غير الموسوم)", merged))
    else:
        merged = neut_paths if neut_paths else code_paths
        sections.append(section("جميع ملفات الشيفرة المتاحة في هذا الإرسال", merged))

    return ("\n".join(intro) + "".join(p for p in sections if p)).strip()


def analyze_game_code(text: str) -> Dict[str, Any]:
    """
    Detect & analyze Unity / GameMaker / Godot GDScript code in plain text (and Scratch-like JSON if embedded).
    Returns a dict safe for JSON serialization.
    """
    result = GameCodeAnalyzer.detect_and_analyze(text)
    return result.to_dict()


def analyze_scratch_project(sb3_path: str) -> Dict[str, Any]:
    """
    Analyze a Scratch .sb3 project file.
    Returns a dict safe for JSON serialization.
    """
    result = GameCodeAnalyzer.analyze_scratch_file(sb3_path)
    return result.to_dict()
