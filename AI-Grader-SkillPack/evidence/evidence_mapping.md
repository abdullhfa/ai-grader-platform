# Evidence Mapping

## Criterion → evidence types

| Short | Primary evidence |
|-------|------------------|
| P3/P4 | Word/PDF design docs |
| P5 | Executable/source + runtime |
| P6 | Test docs + presentation + runtime/playtest |
| M2 | Reviewer feedback records |
| M3/D2/D3 | Refinement + runtime |

## Engine → artifact keys

| Engine | Signatures |
|--------|------------|
| Scratch | `.sb3`, `.sb2` |
| GameMaker | `.yyp`, `.gml`, `data.win` |
| Godot | `project.godot`, `.pck`, `.gd` |
| Unity | `Assets/`, `.unity` |
| HTML5 | `index.html` + wasm/js |

Central module: `app/game_engine_signatures.py`
