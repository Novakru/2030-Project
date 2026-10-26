"""Collect and audit original publication XDLs without rewriting them or inventing success labels."""
from __future__ import annotations

import binascii
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from lxml import etree

from .archives import HTTPRangeReader
from .io import ROOT, digest, read_json, read_jsonl, write_json, write_jsonl


def _updated_xdl(info):
    parts = PurePosixPath(info.filename).parts
    return (len(parts) == 5 and parts[0] in ("successful_reactions", "translated_XDLs")
            and parts[2:4] == ("Procedure", "updated") and parts[-1].lower().endswith(".xdl"))


def inspect_xdl(blob, graph=None):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True)
    document = etree.fromstring(blob, parser)
    if document.getroottree().docinfo.doctype:
        raise ValueError("Publication XML has a forbidden DOCTYPE")
    synthesis = document if document.tag == "Synthesis" else document.find("Synthesis")
    if synthesis is None:
        raise ValueError("Missing Synthesis section")
    absent = [name for name in ("Hardware", "Reagents", "Procedure") if synthesis.find(name) is None]
    if absent:
        raise ValueError("Missing sections: " + ",".join(absent))
    hardware = {x.get("id") for x in synthesis.findall("Hardware/Component")}
    cartridge_chemicals = {x.get("chemical") for x in synthesis.findall("Hardware/Component") if x.get("chemical")}
    reagents = {x.get("name") for x in synthesis.findall("Reagents/Reagent")}
    graph_nodes = {str(n.get("id")) for n in (graph or {}).get("nodes", [])}
    graph_reagents = {n.get("chemical") for n in (graph or {}).get("nodes", []) if n.get("chemical")}
    unknown, placeholders, steps = [], [], Counter()
    for index, element in enumerate(synthesis.find("Procedure").iter()):
        if not isinstance(element.tag, str) or element.tag in ("Procedure", "Prep", "Reaction", "Workup", "Purification"):
            continue
        steps[element.tag] += 1
        for key, value in element.attrib.items():
            allowed = None
            if key in ("vessel", "from_vessel", "to_vessel", "filtrate_vessel", "separation_vessel", "waste_phase_to_vessel"):
                allowed = hardware | graph_nodes
            elif key in ("reagent", "solvent", "rinsing_solvent", "eluting_solvent"):
                allowed = reagents | graph_reagents
            elif key == "through":
                allowed = hardware | cartridge_chemicals | reagents | graph_nodes | graph_reagents
            if allowed is not None and value not in allowed:
                entry = {"step_index": index, "operation": element.tag, "attribute": key, "value": value}
                (placeholders if value.lower() in ("undefined", "none", "null", "") else unknown).append(entry)
    # Remove metadata before checking whether two source programs are identical.
    metadata = synthesis.find("Metadata")
    if metadata is not None:
        synthesis.remove(metadata)
    canonical = etree.tostring(synthesis, method="c14n", with_comments=False)
    return {"xml_parse_valid": True, "canonical_xml_sha256": digest(canonical),
            "step_inventory": dict(steps), "unresolved_references": unknown, "placeholder_references": placeholders,
            "graph_present": graph is not None, "platform_compilation": "not_checked_by_static_inspector",
            "full_feasibility_certified": False}


def audit_publications():
    """Offline integrity and static reference checks, separately from ORD/gold acceptance."""
    manifest = read_json(ROOT / "data/publications/members.lock.json")
    failures, counts, rows = [], Counter(), []
    for member in manifest["members"]:
        path = ROOT / member["path"]
        if not path.exists() or digest(path.read_bytes()) != member["sha256"]:
            failures.append("member_checksum:" + member["path"])
    for record in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl"):
        graphs = []
        for member in record["resources"]:
            if member["path"].endswith(".json"):
                graph = read_json(ROOT / member["path"])
                if isinstance(graph, dict) and isinstance(graph.get("nodes"), list):
                    graphs.append(graph)
        quality = inspect_xdl((ROOT / record["raw_xdl_path"]).read_bytes(), graphs[0] if len(graphs) == 1 else None)
        counts["records_checked"] += 1
        counts["with_unresolved_references"] += bool(quality["unresolved_references"])
        counts["with_placeholder_references"] += bool(quality["placeholder_references"])
        if record["label"]["feasible"] is not None or record["benchmark_eligible"]:
            failures.append("unsupported_publication_acceptance_claim:" + record["id"])
        rows.append({"id": record["id"], "source_case": record["source"]["case"], "partition": record["source_partition"], **quality})
    result = {"passed": not failures, "failures": failures, "counts": dict(counts), "records": rows,
              "claim": "Member integrity and static symbols only. Unresolved references may require platform-specific resolution; no gold promotion."}
    prepared = ROOT / "data/publications/candidates.jsonl"
    if prepared.exists():
        import jsonpatch
        canonical_hashes = set()
        by_path = {m["path"]: m["sha256"] for m in manifest["members"]}
        for candidate in read_jsonl(prepared):
            counts["prepared_candidates_checked"] += 1
            raw = (ROOT / candidate["raw_xdl_path"]).read_bytes()
            xml = (ROOT / candidate["xdl_path"]).read_bytes()
            if digest(raw) != by_path.get(candidate["raw_xdl_path"]) or digest(xml) != candidate["xdl_sha256"]:
                failures.append("prepared_checksum:" + candidate["id"])
            if jsonpatch.apply_patch({"xdl": raw.decode("utf-8-sig")}, candidate["diff"]) != {"xdl": xml.decode("utf-8")}:
                failures.append("representation_patch_replay:" + candidate["id"])
            canonical = inspect_xdl(xml)["canonical_xml_sha256"]
            if canonical in canonical_hashes:
                failures.append("prepared_duplicate:" + candidate["id"])
            canonical_hashes.add(canonical)
            if candidate["benchmark_eligible"] or candidate["label"]["feasible"] is not None:
                failures.append("unreviewed_publication_promoted:" + candidate["id"])
    result.update(passed=not failures, counts=dict(counts))
    write_json(ROOT / "reports/publication_audit.json", result)
    return {"passed": result["passed"], "counts": result["counts"], "failures": failures}


def repair_representation(blob):
    """Only mechanical tag-case and uniquely resolvable symbol-whitespace repairs."""
    text = blob.decode("utf-8-sig")
    edits = []
    # The source contains <ASync> closed by </Async>; the other source programs
    # use Async. Do not guess new steps or chemical parameters to repair XML.
    if "<ASync>" in text and "</Async>" in text and "</ASync>" not in text:
        text = text.replace("<ASync>", "<Async>")
        edits.append({"kind": "tag_case", "before": "<ASync>", "after": "<Async>"})
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    tree = etree.fromstring(text.encode("utf-8"), parser).getroottree()
    if tree.docinfo.doctype:
        raise ValueError("DOCTYPE is not allowed")
    root = tree.getroot()
    synthesis = root if root.tag == "Synthesis" else root.find("Synthesis")
    if synthesis is None:
        raise ValueError("Missing Synthesis")
    symbols = {r.get("name") for r in synthesis.findall("Reagents/Reagent")} | {r.get("id") for r in synthesis.findall("Hardware/Component")}
    for element in synthesis.find("Procedure").iter():
        if not isinstance(element.tag, str):
            continue
        for attribute in ("reagent", "vessel", "from_vessel", "to_vessel", "solvent", "rinsing_solvent", "eluting_solvent"):
            value = element.get(attribute)
            if value and value not in symbols and value.strip() in symbols:
                element.set(attribute, value.strip())
                edits.append({"kind": "symbol_whitespace", "xpath": tree.getpath(element),
                              "attribute": attribute, "before": value, "after": value.strip()})
    if any(edit["kind"] == "symbol_whitespace" for edit in edits):
        text = etree.tostring(tree, encoding="unicode")
    return text.encode("utf-8"), edits


def prepare_publication_candidates():
    import jsonpatch
    manifest = read_json(ROOT / "data/publications/members.lock.json")
    records = {r["raw_xdl_path"]: r for r in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl")}
    candidates, quarantined, seen = [], [], set()
    for member in manifest["members"]:
        if not member["path"].endswith(".xdl"):
            continue
        raw = (ROOT / member["path"]).read_bytes()
        if digest(raw) != member["sha256"]:
            raise ValueError("Publication source checksum changed")
        case_id = Path(member["path"]).parent.name
        origin = records.get(member["path"])
        try:
            corrected, edits = repair_representation(raw)
            graph = None
            if origin:
                graph_options = []
                for item in origin["resources"]:
                    if item["path"].endswith(".json"):
                        value = read_json(ROOT / item["path"])
                        if isinstance(value, dict) and isinstance(value.get("nodes"), list):
                            graph_options.append(value)
                graph = graph_options[0] if len(graph_options) == 1 else None
            quality = inspect_xdl(corrected, graph)
            if quality["unresolved_references"] or quality["placeholder_references"]:
                quarantined.append({"id": case_id, "raw_xdl_path": member["path"], "quality": quality})
                continue
            if quality["canonical_xml_sha256"] in seen:
                continue
            seen.add(quality["canonical_xml_sha256"])
            folder = ROOT / "data/xdl/publication"
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / (case_id + ".xdl")
            target.write_bytes(corrected)
            patch = jsonpatch.make_patch({"xdl": raw.decode("utf-8-sig")}, {"xdl": corrected.decode("utf-8")}).patch
            partition = member["archive_member"].split("/")[0]
            candidates.append({"id": case_id, "source": {"db": "PUBLISHED_CHEMPUTER", "doi": "10.5281/zenodo.6534009", "license": "cc-by-4.0", "archive_member": member["archive_member"]},
                               "source_partition": partition, "raw_xdl_path": member["path"], "raw_sha256": member["sha256"],
                               "xdl_path": str(target.relative_to(ROOT)).replace("\\", "/"), "xdl_sha256": digest(corrected),
                               "representation_edits": edits, "diff": patch, "quality": quality,
                               "label": {"feasible": None, "p_infeasible": None}, "benchmark_eligible": False})
        except (ValueError, etree.XMLSyntaxError) as error:
            quarantined.append({"id": case_id, "raw_xdl_path": member["path"], "error": str(error)[:400]})
    write_jsonl(ROOT / "data/publications/candidates.jsonl", candidates)
    write_jsonl(ROOT / "data/publications/quarantined.jsonl", quarantined)
    result = {"static_valid_unique_xdl": len(candidates), "quarantined": len(quarantined),
              "mechanically_repaired": sum(bool(c["representation_edits"]) for c in candidates),
              "source_partitions": dict(Counter(c["source_partition"] for c in candidates)),
              "strict_gold": 0, "claim": "Static XML and symbol checks only. Separate platform_validation records hold any subsequent compiler checks; no full chemical/hardware certification."}
    write_json(ROOT / "reports/publication_candidates.json", result)
    folder = (ROOT / "data/xdl/publication").resolve()
    expected = {c["id"] + ".xdl" for c in candidates}
    if not folder.is_relative_to((ROOT / "data").resolve()):
        raise ValueError("Publication output cleanup escapes data directory")
    for path in folder.glob("chemputer_2022_*.xdl"):
        if path.name not in expected and path.is_file() and path.resolve().is_relative_to(folder):
            path.unlink()
    return result


def collect_chemputer():
    record = read_json(ROOT / "data/publications.lock.json")["records"][0]
    archive = next(a for a in record["archives"] if a["key"] == "reaction_data.zip")
    output, members, errors = [], [], []
    with HTTPRangeReader(archive["url"], archive["size"]) as remote:
        with zipfile.ZipFile(remote) as source:
            selected = sorted((i for i in source.infolist() if _updated_xdl(i)), key=lambda i: i.filename)
            for number, entry in enumerate(selected, 1):
                parts = PurePosixPath(entry.filename).parts
                case_id = "chemputer_2022_" + digest(entry.filename)[:16]
                folder = ROOT / "data/upstream/chemputer_2022/procedures" / case_id
                folder.mkdir(parents=True, exist_ok=True)
                related = [i for i in source.infolist() if PurePosixPath(i.filename).parent == PurePosixPath(entry.filename).parent
                           and PurePosixPath(i.filename).suffix.lower() in (".xdl", ".json", ".txt", ".xdlexe")]
                resources, blobs = [], {}
                for info in sorted(related, key=lambda i: i.filename):
                    if info.file_size > 2097152:
                        errors.append({"member": info.filename, "error": "member_exceeds_2MiB_review_limit"})
                        continue
                    name = PurePosixPath(info.filename).name
                    if any(c in name for c in '<>:"/\\|?*'):
                        name = digest(info.filename)[:12] + PurePosixPath(name).suffix
                    target = folder / name
                    blob = target.read_bytes() if target.exists() else b""
                    if not target.exists() or len(blob) != info.file_size or binascii.crc32(blob) & 0xffffffff != info.CRC:
                        blob = source.read(info)  # zipfile validates the full member CRC on read.
                        target.write_bytes(blob)
                    member = {"archive": archive["key"], "archive_member": info.filename,
                              "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                              "sha256": digest(blob), "crc32": info.CRC, "size": len(blob)}
                    resources.append(member)
                    members.append(member)
                    blobs[info.filename] = blob
                try:
                    raw = blobs[entry.filename]
                    graph_resources = [r for r in resources if r["path"].lower().endswith(".json")]
                    graphs = []
                    for r in graph_resources:
                        candidate = json.loads((ROOT / r["path"]).read_text(encoding="utf-8-sig"))
                        if isinstance(candidate, dict) and isinstance(candidate.get("nodes"), list):
                            graphs.append(candidate)
                    quality = inspect_xdl(raw, graphs[0] if len(graphs) == 1 else None)
                    origin = "author_reported_successful_partition" if parts[0] == "successful_reactions" else "author_translation_not_executed"
                    output.append({"id": case_id, "source": {"db": "PUBLISHED_CHEMPUTER", "doi": record["doi"],
                                   "publication_doi": record["publication_doi"], "license": record["license"],
                                   "url": "https://zenodo.org/records/" + str(record["record_id"]),
                                   "archive_member": entry.filename, "case": parts[1]},
                                   "source_partition": parts[0], "evidence_type": origin,
                                   "raw_xdl_path": next(r["path"] for r in resources if r["archive_member"] == entry.filename),
                                   "resources": resources, "quality": quality,
                                   "label": {"feasible": None, "label_type": "unreviewed_publication_reference", "p_infeasible": None},
                                   "benchmark_eligible": False})
                except (ValueError, KeyError, etree.XMLSyntaxError) as error:
                    errors.append({"member": entry.filename, "error": str(error)[:400]})
                print(f"Publication {number}/{len(selected)}; records={len(output)}; HTTP bytes={remote.bytes_downloaded}", flush=True)
        transfer = {"bytes_downloaded": remote.bytes_downloaded, "range_requests": remote.requests_made}
    unique = {p["quality"]["canonical_xml_sha256"] for p in output}
    write_jsonl(ROOT / "data/publications/chemputer_2022.jsonl", output)
    write_json(ROOT / "data/publications/members.lock.json", {"record_id": record["record_id"], "archive_checksum_reported_by_publisher": archive["checksum"],
               "full_archive_checksum_verified": False, "member_integrity": "ZIP CRC32 plus frozen member SHA256; full archive was not downloaded", "members": members})
    summary = {"source_records": len(output), "unique_source_programs": len(unique), "partitions": dict(Counter(p["source_partition"] for p in output)),
               "with_graph": sum(p["quality"]["graph_present"] for p in output),
               "with_unresolved_references": sum(bool(p["quality"]["unresolved_references"]) for p in output),
               "with_placeholder_references": sum(bool(p["quality"]["placeholder_references"]) for p in output),
               "strict_gold": 0, "errors": errors, **transfer,
               "claim": "Publication references retain author partitions; reported success and compiled artifacts do not establish this project's gold acceptance."}
    write_json(ROOT / "reports/publication_corpus.json", summary)
    return summary
