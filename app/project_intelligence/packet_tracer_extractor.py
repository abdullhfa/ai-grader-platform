"""
Deterministic Cisco Packet Tracer (.pkt) intake — no AI / semantic grading.

Legacy .pkt: XOR-per-byte (decreasing length key) + zlib-compressed XML (ptexplorer).
Newer encrypted builds may fail decode; extraction reports decode status only.
"""
from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

PACKET_TRACER_EXTRACTOR_VERSION = "1.0"
PACKET_TRACER_EXT = ".pkt"
MAX_PKT_FILES = 5
MAX_XML_CHARS = 4_000_000

_DEVICE_TYPE_RE = re.compile(
    r"<TYPE[^>]*>\s*([^<]+?)\s*</TYPE>",
    re.IGNORECASE,
)
_DEVICE_TAG_RE = re.compile(r"<DEVICE\b", re.IGNORECASE)
_NETWORK_TAG_RE = re.compile(r"<NETWORK\b", re.IGNORECASE)
_INTERFACE_RE = re.compile(
    r"(?:FastEthernet\d*|GigabitEthernet\d*|Ethernet\d*|Serial\d*|"
    r"Loopback\d*|Vlan\d+|interface\s+\d|INTERFACE)",
    re.IGNORECASE,
)
_VLAN_RE = re.compile(r"\b(?:vlan|VLAN)[\s\-_]*(\d{1,4})\b", re.IGNORECASE)
_STATIC_ROUTE_RE = re.compile(
    r"\b(?:staticRoute|STATIC_ROUTE|ip\s+route|network\s+\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+"
    r"(?:mask|255\.|0\.0\.0\.0))\b",
    re.IGNORECASE,
)
_ROUTING_PROTOCOL_RE = re.compile(
    r"\b(RIP(?:v2)?|OSPF(?:v3)?|EIGRP|BGP|IS-IS|RIPng)\b",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
)
_SUBNET_MASK_RE = re.compile(
    r"\b(?:SubnetMask|subnetMask|MASK)[^>]*>([^<]+)<|"
    r"\b(?:255\.(?:255\.)?(?:255\.)?\d+|255\.255\.255\.0)\b",
    re.IGNORECASE,
)

_ROUTER_HINTS = frozenset(
    {"router", "wireless router", "1841", "1941", "2811", "2911", "4321"}
)
_SWITCH_HINTS = frozenset(
    {"switch", "multilayer switch", "2960", "3560", "3650", "9300"}
)
_PC_HINTS = frozenset({"pc", "laptop", "tablet", "smartphone", "end device", "iot"})


def encode_legacy_pkt_bytes(xml_text: str) -> bytes:
    """Build legacy-format .pkt bytes from XML (calibration fixtures only)."""
    in_data = xml_text.encode("utf-8")
    i_size = len(in_data)
    header = i_size.to_bytes(4, "big")
    out_data = header + zlib.compress(in_data)
    o_size = len(out_data)
    xor_out = bytearray()
    for byte in out_data:
        xor_out.append((byte ^ o_size).to_bytes(4, "little")[0])
        o_size -= 1
    return bytes(xor_out)


def decode_legacy_pkt_bytes(data: bytes) -> Tuple[Optional[str], Optional[str]]:
    """Decode legacy XOR+zlib .pkt payload to XML text."""
    if not data:
        return None, "empty_file"
    in_data = bytearray(data)
    i_size = len(in_data)
    out = bytearray()
    for byte in in_data:
        out.append((byte ^ i_size).to_bytes(4, "little")[0])
        i_size -= 1
    if len(out) < 8:
        return None, "truncated_payload"
    try:
        xml_bytes = zlib.decompress(bytes(out[4:]))
    except zlib.error as exc:
        return None, f"zlib_decompress_failed:{exc.__class__.__name__}"
    try:
        text = xml_bytes.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return None, f"xml_decode_failed:{exc.__class__.__name__}"
    if "<PACKETTRACER" not in text.upper() and "<NETWORK" not in text.upper():
        return None, "decoded_not_packet_tracer_xml"
    return text[:MAX_XML_CHARS], None


def _load_pkt_xml(path: Path) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Return (xml_text, decode_method, error).
    decode_method: legacy_xor_zlib | plain_xml | failed
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, "failed", f"unreadable:{exc.__class__.__name__}"

    if not raw:
        return None, "failed", "empty_file"

    stripped = raw.lstrip()
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<PACKETTRACER"):
        try:
            text = raw.decode("utf-8", errors="replace")[:MAX_XML_CHARS]
            return text, "plain_xml", None
        except Exception as exc:  # noqa: BLE001
            return None, "failed", f"plain_xml_decode:{exc.__class__.__name__}"

    text, err = decode_legacy_pkt_bytes(raw)
    if text:
        return text, "legacy_xor_zlib", None
    return None, "failed", err or "decode_failed"


def _classify_device_type(label: str) -> str:
    low = label.strip().lower()
    if any(h in low for h in _ROUTER_HINTS) and "switch" not in low:
        return "router"
    if any(h in low for h in _SWITCH_HINTS):
        return "switch"
    if any(h in low for h in _PC_HINTS):
        return "pc"
    return "other"


def _valid_host_ipv4(ip: str) -> bool:
    if ip in ("0.0.0.0", "255.255.255.255"):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    if octets[0] in (0, 127, 255):
        return False
    if octets[3] in (0, 255):
        return False
    return True


def _extract_signals_from_xml(xml_text: str) -> Dict[str, Any]:
    device_types: List[str] = []
    for m in _DEVICE_TYPE_RE.finditer(xml_text):
        device_types.append(m.group(1).strip())

    device_tag_count = len(_DEVICE_TAG_RE.findall(xml_text))
    device_count = max(device_tag_count, len(device_types))

    router_count = sum(1 for t in device_types if _classify_device_type(t) == "router")
    switch_count = sum(1 for t in device_types if _classify_device_type(t) == "switch")
    pc_count = sum(1 for t in device_types if _classify_device_type(t) == "pc")

    ips: Set[str] = set()
    for m in _IPV4_RE.finditer(xml_text):
        ip = m.group(0)
        if _valid_host_ipv4(ip):
            ips.add(ip)

    subnets_detected = len(_SUBNET_MASK_RE.findall(xml_text))
    if subnets_detected == 0 and ips:
        prefixes = { ".".join(ip.split(".")[:3]) for ip in ips }
        subnets_detected = len(prefixes)

    interfaces_detected = len(_INTERFACE_RE.findall(xml_text))
    vlan_ids = {m.group(1) for m in _VLAN_RE.finditer(xml_text)}
    static_hits = len(_STATIC_ROUTE_RE.findall(xml_text))
    protocols = sorted({m.group(1).upper() for m in _ROUTING_PROTOCOL_RE.finditer(xml_text)})

    topology_detected = bool(
        _NETWORK_TAG_RE.search(xml_text)
        or device_count >= 2
        or (router_count + switch_count + pc_count) >= 2
    )

    ip_configurations_detected = bool(ips) or bool(
        re.search(r"<IP\b|<IPAddress\b|ipv4Address", xml_text, re.I)
    )
    static_routes_detected = static_hits > 0 or bool(
        re.search(r"<ROUTING\b|<STATIC", xml_text, re.I) and "route" in xml_text.lower()
    )

    noise_flags: List[Dict[str, str]] = []
    if topology_detected and not ip_configurations_detected:
        noise_flags.append({"flag": "topology_without_ip_configuration"})
    if static_routes_detected and interfaces_detected == 0:
        noise_flags.append({"flag": "routing_without_interfaces"})
    if (router_count + switch_count) > 0 and pc_count == 0 and device_count >= 2:
        noise_flags.append({"flag": "no_end_devices_detected"})

    return {
        "device_count": device_count,
        "router_count": router_count,
        "switch_count": switch_count,
        "pc_count": pc_count,
        "topology_detected": topology_detected,
        "ip_configurations_detected": ip_configurations_detected,
        "unique_ip_count": len(ips),
        "subnets_detected": subnets_detected,
        "interfaces_detected": interfaces_detected,
        "vlan_count": len(vlan_ids),
        "static_routes_detected": static_routes_detected,
        "routing_protocols": protocols,
        "noise_flags": noise_flags,
    }


def extract_single_pkt_file(path: Path) -> Dict[str, Any]:
    xml_text, decode_method, err = _load_pkt_xml(path)
    row: Dict[str, Any] = {
        "path": str(path),
        "basename": path.name,
        "decode_method": decode_method,
        "decode_error": err,
        "readable": xml_text is not None,
    }
    if xml_text:
        row["signals"] = _extract_signals_from_xml(xml_text)
        row["xml_char_count"] = len(xml_text)
    else:
        row["signals"] = None
        flags = [{"flag": "pkt_decode_failed"}]
        if err == "empty_file":
            flags = [{"flag": "pkt_empty_or_unreadable"}]
        row["noise_flags"] = flags
    return row


def list_packet_tracer_files(file_paths: Sequence[Path]) -> List[Path]:
    out: List[Path] = []
    for fp in sorted(file_paths, key=lambda p: str(p).lower()):
        try:
            if fp.suffix.lower() == PACKET_TRACER_EXT and fp.is_file():
                out.append(fp.resolve())
        except OSError:
            continue
    return out[:MAX_PKT_FILES]


def _merge_extractions(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    readable = [r for r in rows if r.get("readable") and isinstance(r.get("signals"), dict)]
    if not readable:
        return {
            "device_count": 0,
            "router_count": 0,
            "switch_count": 0,
            "pc_count": 0,
            "topology_detected": False,
            "ip_configurations_detected": False,
            "subnets_detected": 0,
            "static_routes_detected": False,
            "routing_protocols": [],
            "unique_ip_count": 0,
            "interfaces_detected": 0,
            "vlan_count": 0,
        }

    def _max(key: str) -> int:
        return max(int((r.get("signals") or {}).get(key) or 0) for r in readable)

    def _any(key: str) -> bool:
        return any(bool((r.get("signals") or {}).get(key)) for r in readable)

    protocols: Set[str] = set()
    for r in readable:
        for p in (r.get("signals") or {}).get("routing_protocols") or []:
            protocols.add(str(p))

    return {
        "device_count": _max("device_count"),
        "router_count": _max("router_count"),
        "switch_count": _max("switch_count"),
        "pc_count": _max("pc_count"),
        "topology_detected": _any("topology_detected"),
        "ip_configurations_detected": _any("ip_configurations_detected"),
        "subnets_detected": _max("subnets_detected"),
        "static_routes_detected": _any("static_routes_detected"),
        "routing_protocols": sorted(protocols),
        "unique_ip_count": _max("unique_ip_count"),
        "interfaces_detected": _max("interfaces_detected"),
        "vlan_count": _max("vlan_count"),
    }


def build_network_evidence_summary(packet_tracer_block: Dict[str, Any]) -> Dict[str, Any]:
    """Academic sufficiency slice — structured counts only, no grading."""
    agg = packet_tracer_block.get("aggregate") or {}
    files = packet_tracer_block.get("pkt_files") or []
    noise: List[Dict[str, str]] = list(packet_tracer_block.get("noise_flags") or [])
    for row in packet_tracer_block.get("extractions") or []:
        if not isinstance(row, dict):
            continue
        for nf in row.get("noise_flags") or []:
            if isinstance(nf, dict) and nf.get("flag"):
                noise.append(nf)
        sig = row.get("signals")
        if isinstance(sig, dict):
            for nf in sig.get("noise_flags") or []:
                if isinstance(nf, dict) and nf.get("flag"):
                    noise.append(nf)

    seen: Set[str] = set()
    deduped: List[Dict[str, str]] = []
    for nf in noise:
        f = nf.get("flag")
        if not f or f in seen:
            continue
        seen.add(f)
        deduped.append({"flag": f})

    return {
        "pkt_file_count": len(files),
        "readable_pkt_count": sum(
            1 for r in (packet_tracer_block.get("extractions") or []) if r.get("readable")
        ),
        "metadata": {
            "device_count": agg.get("device_count"),
            "router_count": agg.get("router_count"),
            "switch_count": agg.get("switch_count"),
            "pc_count": agg.get("pc_count"),
        },
        "topology": {"topology_detected": agg.get("topology_detected")},
        "addressing": {
            "ip_configurations_detected": agg.get("ip_configurations_detected"),
            "subnets_detected": agg.get("subnets_detected"),
            "unique_ip_count": agg.get("unique_ip_count"),
            "interfaces_detected": agg.get("interfaces_detected"),
            "vlan_count": agg.get("vlan_count"),
        },
        "routing": {
            "static_routes_detected": agg.get("static_routes_detected"),
            "routing_protocols": agg.get("routing_protocols") or [],
        },
        "noise_flags": sorted(deduped, key=lambda x: x["flag"]),
        "limitations_ar": (
            "استخراج حتمي من XML داخل .pkt (تنسيق قديم XOR+zlib)؛ "
            "لا يقيّم صحة التصميم أو التوجيه؛ إصدارات PT المشفّرة حديثاً قد تفشل فك التشفير."
        ),
    }


def build_packet_tracer_evidence_items(
    packet_tracer_block: Dict[str, Any],
    engines: List[str],
) -> List[Dict[str, Any]]:
    """Normalized evidence_layer rows (presence / structure only)."""
    engine = "cisco_packet_tracer" if "cisco_packet_tracer" in engines else (
        engines[0] if engines else "unknown"
    )
    agg = packet_tracer_block.get("aggregate") or {}
    items: List[Dict[str, Any]] = []
    for row in packet_tracer_block.get("extractions") or []:
        if not isinstance(row, dict) or not row.get("readable"):
            continue
        sig = row.get("signals") or {}
        items.append(
            {
                "evidence_type": "packet_tracer_topology",
                "engine": engine,
                "system": None,
                "confidence": None,
                "execution_evidence": "packet_tracer_file",
                "evidence_count": sig.get("device_count"),
                "sources": [str(row.get("path") or "")],
                "basename": row.get("basename"),
                "decode_method": row.get("decode_method"),
                "topology_detected": sig.get("topology_detected"),
                "ip_configurations_detected": sig.get("ip_configurations_detected"),
                "subnets_detected": sig.get("subnets_detected"),
                "static_routes_detected": sig.get("static_routes_detected"),
                "routing_protocols": sig.get("routing_protocols") or [],
                "device_count": sig.get("device_count"),
                "router_count": sig.get("router_count"),
                "switch_count": sig.get("switch_count"),
                "pc_count": sig.get("pc_count"),
                "criterion_candidates": [],
                "weight": 0.0,
            }
        )
    if not items and packet_tracer_block.get("pkt_files"):
        items.append(
            {
                "evidence_type": "packet_tracer_topology",
                "engine": engine,
                "system": None,
                "confidence": None,
                "execution_evidence": "packet_tracer_file_unreadable",
                "evidence_count": 0,
                "sources": list(packet_tracer_block.get("pkt_files") or [])[:MAX_PKT_FILES],
                "topology_detected": False,
                "ip_configurations_detected": False,
                "subnets_detected": 0,
                "static_routes_detected": False,
                "routing_protocols": [],
                "criterion_candidates": [],
                "weight": 0.0,
            }
        )
    if agg.get("topology_detected") and items:
        items[0]["aggregate_snapshot"] = {
            "device_count": agg.get("device_count"),
            "routing_protocols": agg.get("routing_protocols"),
        }
    return items


def extract_packet_tracer_evidence(file_paths: Sequence[Path]) -> Dict[str, Any]:
    """
    Scan submission paths for .pkt files and emit deterministic network evidence.
    """
    pkt_paths = list_packet_tracer_files(file_paths)
    extractions = [extract_single_pkt_file(p) for p in pkt_paths]
    aggregate = _merge_extractions(extractions)

    noise_flags: List[Dict[str, str]] = []
    if pkt_paths and not any(r.get("readable") for r in extractions):
        noise_flags.append({"flag": "all_pkt_files_unreadable"})
    if not pkt_paths:
        noise_flags.append({"flag": "no_pkt_files_found"})

    return {
        "version": 1,
        "extractor_version": PACKET_TRACER_EXTRACTOR_VERSION,
        "pkt_files": [str(p) for p in pkt_paths],
        "extractions": extractions,
        "aggregate": aggregate,
        "network_evidence_summary": {},  # filled by build_network_evidence_summary
        "noise_flags": noise_flags,
        "notes_ar": (
            "تحليل Packet Tracer حتمي من بنية الملف فقط؛ "
            "لا يستبدل تقييم المعلم ولا يستنتج صحة الشبكة."
        ),
    }


def finalize_packet_tracer_block(block: Dict[str, Any]) -> Dict[str, Any]:
    """Attach network_evidence_summary after aggregate is known."""
    if not block:
        return block
    block = dict(block)
    block["network_evidence_summary"] = build_network_evidence_summary(block)
    return block
