# Architecture Prompt

When adding a new grading layer:

1. Document position in pipeline (dependency_graph.md)
2. If it sets `achieved=True`, ensure Runtime Gate still runs after
3. Prefer extending `game_engine_signatures.py` over duplicating extensions
4. Update skill pack CHANGELOG
