"""
Build synthetic legacy .pkt fixtures and run project_profile + evidence_layer.

Usage (repo root):
  python -m app.calibration.mini_validation_packet_tracer.run_mini_validation_packet_tracer

Observation-only — fill observed_friction / unexpected_result after human review.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.project_intelligence.packet_tracer_extractor import encode_legacy_pkt_bytes

_XML_VALID = """<?xml version="1.0"?>
<PACKETTRACER5>
<VERSION>5.3.0.0073</VERSION>
<NETWORK>
<DEVICES>
<DEVICE><ENGINE><TYPE model="2811">Router</TYPE><NAME>R1</NAME></ENGINE></DEVICE>
<DEVICE><ENGINE><TYPE model="2960">Switch</TYPE><NAME>SW1</NAME></ENGINE></DEVICE>
<DEVICE><ENGINE><TYPE>PC</TYPE><NAME>PC1</NAME></ENGINE></DEVICE>
<DEVICE><ENGINE><TYPE>PC</TYPE><NAME>PC2</NAME></ENGINE></DEVICE>
</DEVICES>
</NETWORK>
<IP>192.168.1.1</IP>
<IP>192.168.1.10</IP>
<IP>192.168.2.20</IP>
<SubnetMask>255.255.255.0</SubnetMask>
<FastEthernet0/0/>
<GigabitEthernet0/1/>
<STATIC_ROUTE>ip route 10.0.0.0 255.255.255.0</STATIC_ROUTE>
<RIP>version 2</RIP>
</PACKETTRACER5>
"""

_XML_TOPOLOGY_ONLY = """<?xml version="1.0"?>
<PACKETTRACER5>
<VERSION>5.3</VERSION>
<NETWORK>
<DEVICES>
<DEVICE><ENGINE><TYPE>Router</TYPE><NAME>R1</NAME></ENGINE></DEVICE>
<DEVICE><ENGINE><TYPE>Switch</TYPE><NAME>SW1</NAME></ENGINE></DEVICE>
<DEVICE><ENGINE><TYPE>PC</TYPE><NAME>PC1</NAME></ENGINE></DEVICE>
</DEVICES>
</NETWORK>
</PACKETTRACER5>
"""

_XML_ROUTING_NO_IF = """<?xml version="1.0"?>
<PACKETTRACER5>
<NETWORK>
<DEVICE><ENGINE><TYPE>Router</TYPE><NAME>R1</NAME></ENGINE></DEVICE>
</NETWORK>
<STATIC_ROUTE>network 10.0.0.0 mask 255.0.0.0</STATIC_ROUTE>
<RIPng>enabled</RIPng>
</PACKETTRACER5>
"""


def _ensure_fixture(case_dir: Path, filename: str, payload: bytes) -> Path:
    case_dir.mkdir(parents=True, exist_ok=True)
    out = case_dir / filename
    out.write_bytes(payload)
    return out


def _bootstrap_case_fixtures(case_id: str, case_dir: Path) -> None:
    if case_id == "case_a_valid_network":
        _ensure_fixture(case_dir, "network_lab.pkt", encode_legacy_pkt_bytes(_XML_VALID))
    elif case_id == "case_b_empty_pkt":
        _ensure_fixture(case_dir, "empty.pkt", b"")
    elif case_id == "case_c_topology_no_ips":
        _ensure_fixture(case_dir, "topology_only.pkt", encode_legacy_pkt_bytes(_XML_TOPOLOGY_ONLY))
    elif case_id == "case_d_routing_no_interfaces":
        _ensure_fixture(case_dir, "routing_only.pkt", encode_legacy_pkt_bytes(_XML_ROUTING_NO_IF))
    elif case_id == "case_e_corrupt_pkt":
        _ensure_fixture(case_dir, "corrupt.pkt", b"\x00\x01\xfe\xcd\xabPKT-GARBAGE\xff" * 40)


def _collect_files(case_dir: Path) -> List[str]:
    return [str(p.resolve()) for p in sorted(case_dir.rglob("*")) if p.is_file()]


def _compact(profile: Dict[str, Any], evidence_layer: Dict[str, Any]) -> Dict[str, Any]:
    pt = profile.get("packet_tracer_evidence") or {}
    agg = pt.get("aggregate") or {}
    pt_items = [
        it
        for it in (evidence_layer.get("items") or [])
        if isinstance(it, dict) and it.get("evidence_type") == "packet_tracer_topology"
    ]
    return {
        "engines_detected": profile.get("engines_detected"),
        "packet_tracer_aggregate": agg,
        "network_evidence_summary": pt.get("network_evidence_summary"),
        "packet_tracer_noise_flags": pt.get("noise_flags"),
        "extractions_head": (pt.get("extractions") or [])[:2],
        "evidence_layer_pt_items": [
            {
                "evidence_type": it.get("evidence_type"),
                "topology_detected": it.get("topology_detected"),
                "ip_configurations_detected": it.get("ip_configurations_detected"),
                "device_count": it.get("device_count"),
                "routing_protocols": it.get("routing_protocols"),
                "static_routes_detected": it.get("static_routes_detected"),
                "execution_evidence": it.get("execution_evidence"),
            }
            for it in pt_items
        ],
    }


def run_all() -> Dict[str, Any]:
    root = Path(__file__).resolve().parent
    template = json.loads((root / "expected_cases.json").read_text(encoding="utf-8"))

    from app.project_intelligence.evidence_schema import build_evidence_layer_from_profile
    from app.project_intelligence.project_profile import build_project_profile

    cases_out: List[Dict[str, Any]] = []
    for entry in template.get("cases") or []:
        cid = entry.get("case_id") or ""
        case_dir = root / "cases" / cid
        case_dir.mkdir(parents=True, exist_ok=True)
        _bootstrap_case_fixtures(cid, case_dir)
        paths = _collect_files(case_dir)
        profile = build_project_profile(paths)
        evidence_layer = build_evidence_layer_from_profile(profile)
        snap = _compact(profile, evidence_layer)
        cases_out.append(
            {
                **entry,
                "actual_behavior": json.dumps(snap, ensure_ascii=False, indent=2),
            }
        )

    return {
        "run_purpose": template.get("run_purpose", ""),
        "cases": cases_out,
        "note": "Fill observed_friction and unexpected_result after manual review.",
    }


def main() -> None:
    out = run_all()
    root = Path(__file__).resolve().parent
    out_path = root / "mini_validation_packet_tracer_last_run.json"
    if out_path.is_file():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        prev_by = {c.get("case_id"): c for c in prev.get("cases") or []}
        for row in out.get("cases") or []:
            cid = row.get("case_id")
            if cid in prev_by:
                for key in ("observed_friction", "unexpected_result", "observation_notes"):
                    if prev_by[cid].get(key):
                        row[key] = prev_by[cid][key]
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
