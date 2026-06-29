# Coding Workflow

## Setup

```bash
cd ai_grader_python
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY, SECRET_KEY
python run_dev_server.py    # http://localhost:5557
```

## Change checklist

1. Identify pipeline stage affected (see dependency_graph.md)
2. Minimize diff — one concern per commit
3. Run targeted tests:
   ```bash
   python -m pytest tests/test_runtime_evidence_gate.py tests/test_btec_criteria_governance.py -q
   ```
4. Restart dev server after backend changes
5. Never commit `.env` or `uploads/students/`

## Branch naming

`fix/runtime-gate-scratch`, `feat/preflight-v4`, `docs/skill-pack`
