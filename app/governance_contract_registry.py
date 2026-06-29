"""
Governance contract registry — counterfactual replay policy profiles.

Contracts define how the same event stream is interpreted under different governance epochs.
Read-only definitions — never mutate live grading state.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

GOVERNANCE_CONTRACT_V1 = "GOVERNANCE_v1"
GOVERNANCE_CONTRACT_V2 = "GOVERNANCE_v2"
DEFAULT_BASELINE_CONTRACT = GOVERNANCE_CONTRACT_V1
DEFAULT_COMPARISON_CONTRACT = GOVERNANCE_CONTRACT_V2

CONTRACTS: Dict[str, Dict[str, Any]] = {
    GOVERNANCE_CONTRACT_V1: {
        "contract_id": GOVERNANCE_CONTRACT_V1,
        "governance_contract": "2.1",
        "reducer_version": "1.0",
        "label_ar": "GOVERNANCE_FREEZE_v1 — runtime gated, L5 required",
        "l4_sandbox_permitted": False,
        "runtime_gated_by_default": True,
        "min_confidence_achievement": 0.93,
        "human_playtest_required_for_execution_criteria": True,
        "smoke_only_blocks_achievement": True,
        "hold_on_insufficient_evidence": True,
    },
    GOVERNANCE_CONTRACT_V2: {
        "contract_id": GOVERNANCE_CONTRACT_V2,
        "governance_contract": "2.2",
        "reducer_version": "1.0",
        "label_ar": "GOVERNANCE_FREEZE_v2 — L4 sandbox observational, lower threshold",
        "l4_sandbox_permitted": True,
        "runtime_gated_by_default": False,
        "min_confidence_achievement": 0.70,
        "human_playtest_required_for_execution_criteria": False,
        "smoke_only_blocks_achievement": True,
        "hold_on_insufficient_evidence": True,
    },
}


def get_contract(contract_id: str) -> Dict[str, Any]:
    cid = (contract_id or DEFAULT_BASELINE_CONTRACT).strip()
    if cid not in CONTRACTS:
        raise ValueError(f"Unknown governance contract: {cid}")
    return dict(CONTRACTS[cid])


def list_contracts() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in CONTRACTS.items()}
