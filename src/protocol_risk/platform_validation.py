"""Parse and compile native XDL with the unmodified, paper-bundled Chemputer SDK."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import functools
import importlib.metadata
import inspect
import io
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from .io import ROOT, digest, read_json, read_jsonl, write_json, write_jsonl
from .native import _graph, parse

PACKAGES = ("xdl", "chemputerxdl", "chempiler", "chemputerapi", "commanduino", "commanduinolabware", "seriallabware")


def origin_for(parent, origins, members):
    if parent["id"] in origins:
        return origins[parent["id"]]
    # A malformed original XML can lack an original parsed index entry, while
    # its mechanically repaired copy and original archive members remain pinned.
    folder = Path(parent["raw_xdl_path"]).parent
    resources = [m for m in members if Path(m["path"]).parent == folder]
    if not any(m["path"] == parent["raw_xdl_path"] and m["sha256"] == parent["raw_sha256"] for m in resources):
        raise ValueError("Native source index cannot be reconstructed from pinned archive members")
    return {"id": parent["id"], "source": parent["source"], "resources": resources}


def legacy_representation(xml):
    """Bridge XML envelopes, explicit unit aliases and otherwise random missing Async IDs."""
    tree = parse(xml)
    root = tree.getroot()
    edits = []
    if root.tag == "XDL" and len(root) == 1 and root[0].tag == "Synthesis":
        root = root[0]
        edits.append({"kind": "unwrap_single_synthesis", "before": "XDL/Synthesis", "after": "Synthesis"})
    reserved_pids = {e.get("pid") for e in root.xpath(".//*[@pid]")}
    for step in root.xpath(".//Procedure//*"):
        if step.tag == "Async" and "pid" not in step.attrib:
            seed = "protocol-risk-async:" + digest(xml.encode("utf-8")) + ":" + tree.getpath(step)
            salt = 0
            while (pid := str(uuid5(NAMESPACE_URL, seed + ":" + str(salt)))) in reserved_pids:
                salt += 1
            step.set("pid", pid)
            reserved_pids.add(pid)
            edits.append({"kind": "deterministic_missing_async_pid", "xpath": tree.getpath(step), "before": None, "after": pid,
                          "basis": "Only an omitted process ID receives a reproducible default; explicit IDs and Await references are preserved."})
        alias = ("speed", "stir_speed", r"rpm") if step.tag == "Stir" else ("amount", "volume", r"m[lL]|L") if step.tag == "Add" else None
        if alias is None:
            continue
        old, new, unit = alias
        value = step.get(old)
        if value and step.get(new) is None and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*(?:" + unit + r")\s*", value, re.I):
            step.set(new, value)
            del step.attrib[old]
            edits.append({"kind": "unit_bearing_attribute_alias", "xpath": tree.getpath(step), "before": old, "after": new, "value": value})
    if not edits:
        return xml, edits
    from lxml import etree
    return etree.tostring(root, encoding="unicode"), edits


def normalize_diagnostics(text):
    text = re.sub(r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d+)?\s*;\s*", "", text)
    return re.sub(r"0x[0-9a-fA-F]+", "<address>", text).replace(str(ROOT), "<workspace>")


def verify_sources():
    manifest = read_json(ROOT / "data/platform_sources.lock.json")
    for member in manifest["members"]:
        if digest((ROOT / member["path"]).read_bytes()) != member["sha256"]:
            raise ValueError("Bundled platform source checksum mismatch: " + member["path"])
    return digest(manifest)


@contextmanager
def offline_platform():
    """Reject device I/O and non-simulation controllers; do not replace SDK checks."""
    verify_sources()
    for package in PACKAGES:
        path = str((ROOT / "data/upstream/platform_2022" / package).resolve())
        if path not in sys.path:
            sys.path.insert(0, path)
    import serial
    import requests  # Initialize urllib3's loopback IPv6 capability probe before the SDK I/O guard.
    calls = {"blocked_io_attempts": 0, "blocked_io_targets": {}, "simulation_controllers": 0}

    def deny(*args, **kwargs):
        calls["blocked_io_attempts"] += 1
        raise RuntimeError("Network/device I/O is disabled in native platform validation")

    with ExitStack() as stack:
        for target in ("socket.create_connection", "socket.getaddrinfo", "socket.socket.connect", "socket.socket.connect_ex",
                       "socket.socket.bind", "socket.socket.send", "socket.socket.sendall", "socket.socket.sendto",
                       "serial.Serial.open", "requests.sessions.Session.request", "builtins.input"):
            def reject(*args, _target=target, **kwargs):
                calls["blocked_io_targets"][_target] = calls["blocked_io_targets"].get(_target, 0) + 1
                return deny(*args, **kwargs)
            stack.enter_context(patch(target, reject))
        from chempiler import Chempiler
        from xdl import XDL
        original = Chempiler.__init__
        signature = inspect.signature(original)

        @functools.wraps(original)
        def simulation_only(self, *args, **kwargs):
            bound = signature.bind(self, *args, **kwargs)
            if bound.arguments.get("simulation") is not True:
                raise RuntimeError("Physical controller initialization is disabled")
            calls["simulation_controllers"] += 1
            return original(self, *args, **kwargs)

        stack.enter_context(patch.object(Chempiler, "__init__", simulation_only))
        yield XDL, calls


def validate_one(parent, origin, XDL, output_folder):
    xml_path = ROOT / parent["xdl_path"]
    blob = xml_path.read_bytes()
    if digest(blob) != parent["xdl_sha256"]:
        raise ValueError("Native XDL input checksum mismatch")
    xml, edits = legacy_representation(blob.decode("utf-8"))
    graph, resource = _graph(origin)
    row = {"id": parent["id"], "source": origin["source"], "source_partition": parent["source_partition"],
           "raw_xdl_path": parent["raw_xdl_path"], "raw_sha256": parent["raw_sha256"],
           "xdl_path": parent["xdl_path"], "xdl_sha256": parent["xdl_sha256"],
           "graph_path": resource["path"] if resource else None, "graph_sha256": resource["sha256"] if resource else None,
           "validation": {"typed_parse": False, "compiled": False, "sanity_checks_enabled": True,
                          "interactive": False, "hardware_execution": False},
           "benchmark_eligible": False, "human_review": "deferred", "full_feasibility_certified": False}
    row["representation_edits"] = edits
    row["parser_input_sha256"] = digest(xml.encode("utf-8"))
    if edits:
        parser_input = ROOT / "data/xdl/platform_input" / (parent["id"] + ".xdl")
        parser_input.parent.mkdir(parents=True, exist_ok=True)
        parser_input.write_bytes(xml.encode("utf-8"))
        row["parser_input_path"] = parser_input.relative_to(ROOT).as_posix()
    else:
        row["parser_input_path"] = parent["xdl_path"]
    stage = "typed_parse"
    try:
        from chemputerxdl.utils import chempiler_singleton
        from commanduinolabware import CommanduinoLabware
        chempiler_singleton.CHEMPILER_SINGLETON = None
        chempiler_singleton._CHEMPILER_SINGLETON_GRAPH_ID = None
        CommanduinoLabware.reset()
        synthesis = XDL(xml, logging_level=50)
        row["validation"]["typed_parse"] = True
        row["top_level_steps"] = len(synthesis.steps)
        row["step_class_modules"] = sorted({type(s).__module__ for s in synthesis.steps})
        if graph is None:
            row["failure"] = {"stage": "graph", "type": "MissingUniqueSourceGraph"}
            return row
        stage = "compile"
        target = output_folder / (parent["id"] + ".xdlexe")
        target.parent.mkdir(parents=True, exist_ok=True)
        synthesis.prepare_for_execution(graph_file=graph, interactive=False, save_path=None, sanity_check=True)
        if not synthesis.compiled:
            raise RuntimeError("SDK did not produce a compiled output")
        from xdl.readwrite.xml_generator import xdl_to_xml_string
        compiled = xdl_to_xml_string(synthesis, graph_hash=synthesis.graph_sha256, full_properties=True, full_tree=True).encode("utf-8")
        target.write_bytes(compiled)
        parse(compiled.decode("utf-8"))
        row["validation"]["compiled"] = True
        row["compiled_path"] = target.relative_to(ROOT).as_posix()
        row["compiled_sha256"] = digest(compiled)
        row["compiled_graph_sha256"] = synthesis.graph_sha256
    except Exception as error:
        row["failure"] = {"stage": stage, "type": type(error).__name__,
                          "message": normalize_diagnostics(str(error))[:1600]}
    return row


def _validate_native_platform():
    source_hash = verify_sources()
    parents = list(read_jsonl(ROOT / "data/publications/candidates.jsonl"))
    origins = {row["id"]: row for row in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl")}
    members = read_json(ROOT / "data/publications/members.lock.json")["members"]
    output = ROOT / "data/compiled/publication"
    work = ROOT / "data/intermediate/platform_work"
    work.mkdir(parents=True, exist_ok=True)
    working_directory = Path.cwd()
    rows, log = [], io.StringIO()
    try:
        os.chdir(work)  # Keep incidental SDK logs away from the project root and original source files.
        with redirect_stdout(log), redirect_stderr(log), offline_platform() as (XDL, calls):
            for parent in parents:
                before = log.tell()
                row = validate_one(parent, origin_for(parent, origins, members), XDL, output)
                row["diagnostics"] = normalize_diagnostics(log.getvalue()[before:])[-6000:]
                rows.append(row)
    finally:
        os.chdir(working_directory)
    write_jsonl(ROOT / "data/publications/platform_validation.jsonl", rows)
    positives = [row for row in rows if row["validation"]["compiled"]]
    expected = {row["compiled_path"] for row in positives}
    for path in output.glob("chemputer_2022_*.xdlexe"):
        if path.relative_to(ROOT).as_posix() not in expected and path.resolve().is_relative_to(output.resolve()):
            path.unlink()
    write_jsonl(ROOT / "data/publications/platform_positives.jsonl", positives)
    runtime = {name: importlib.metadata.version(name) for name in
               ("networkx", "lxml", "numpy", "scipy", "scikit-image", "opencv-contrib-python-headless", "python-socketio")}
    result = {"programs_checked": len(rows), "typed_parse_passed": sum(row["validation"]["typed_parse"] for row in rows),
              "compiled": len(positives), "failed": len(rows) - len(positives),
              "failure_stages": dict(Counter(row["failure"]["stage"] for row in rows if "failure" in row)),
              "compiled_source_partitions": dict(Counter(row["source_partition"] for row in positives)),
              "input_representation_adapted": sum(bool(row["representation_edits"]) for row in rows),
              "platform": "unmodified compiler source bundled with Science 2022 publication",
              "bundled_xdl_version": "0.5.0", "bundled_chemputerxdl_version": "1.0.0",
              "source_manifest_sha256": source_hash, "python_version": platform.python_version(), "runtime": runtime,
              "python_hash_seed": os.environ.get("PYTHONHASHSEED", "random"),
              **calls, "full_feasibility_certified": False, "human_review": "deferred",
              "claim": "Typed parsing, source-graph compilation and upstream sanity checks; controller initialization restricted to simulation. No hardware execution or experimental replication."}
    write_json(ROOT / "reports/native_platform.json", result)
    return result


def validate_native_platform():
    """Use a fresh SDK process so its global loggers and device caches cannot leak across builds."""
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run([sys.executable, "-m", "protocol_risk.platform_validation"], cwd=ROOT,
                            env=environment, capture_output=True, text=True, encoding="utf-8", timeout=300)
    if result.returncode:
        raise RuntimeError("Native platform worker failed: " + result.stderr[-3000:])
    return read_json(ROOT / "reports/native_platform.json")


def audit_native_platform():
    """Check pinned inputs, representation adapters and compiled output inventory."""
    source_hash = verify_sources()
    summary = read_json(ROOT / "reports/native_platform.json")
    rows = list(read_jsonl(ROOT / "data/publications/platform_validation.jsonl"))
    positives = list(read_jsonl(ROOT / "data/publications/platform_positives.jsonl"))
    parents = {r["id"]: r for r in read_jsonl(ROOT / "data/publications/candidates.jsonl")}
    origins = {r["id"]: r for r in read_jsonl(ROOT / "data/publications/chemputer_2022.jsonl")}
    members = read_json(ROOT / "data/publications/members.lock.json")["members"]
    failures = []
    if len(rows) != len(parents) or {r["id"] for r in rows} != set(parents):
        failures.append("native_platform_parent_inventory")
    if summary["source_manifest_sha256"] != source_hash:
        failures.append("native_platform_source_manifest")
    for row in rows:
        parent = parents[row["id"]]
        blob = (ROOT / parent["xdl_path"]).read_bytes()
        xml, edits = legacy_representation(blob.decode("utf-8"))
        origin = origin_for(parent, origins, members)
        _, resource = _graph(origin)
        if (digest(blob) != row["xdl_sha256"] or row["xdl_sha256"] != parent["xdl_sha256"]
                or row["raw_sha256"] != parent["raw_sha256"] or row["source"] != origin["source"]
                or row["source_partition"] != parent["source_partition"]):
            failures.append("native_platform_source_binding:" + row["id"])
        if (edits != row["representation_edits"] or digest(xml.encode("utf-8")) != row["parser_input_sha256"]
                or (ROOT / row["parser_input_path"]).read_bytes() != xml.encode("utf-8")):
            failures.append("native_platform_adapter_replay:" + row["id"])
        if resource and (row["graph_path"] != resource["path"] or row["graph_sha256"] != resource["sha256"]):
            failures.append("native_platform_graph_binding:" + row["id"])
        if row["validation"]["compiled"]:
            compiled = (ROOT / row["compiled_path"]).read_bytes()
            if (not resource or digest(compiled) != row["compiled_sha256"] or not row["validation"]["typed_parse"]
                    or parse(compiled.decode("utf-8")).getroot().get("graph_sha256") != row["compiled_graph_sha256"]):
                failures.append("native_platform_compiled_output:" + row["id"])
        if (row["benchmark_eligible"] or row["full_feasibility_certified"] or row["validation"]["hardware_execution"]
                or row["validation"]["interactive"] or not row["validation"]["sanity_checks_enabled"]):
            failures.append("native_platform_unsupported_claim:" + row["id"])
    if positives != [r for r in rows if r["validation"]["compiled"]] or len(positives) != summary["compiled"]:
        failures.append("native_platform_positive_partition")
    result = {"passed": not failures, "programs_checked": len(rows), "compiled_checked": len(positives), "failures": failures}
    write_json(ROOT / "reports/native_platform_audit.json", result)
    return result


if __name__ == "__main__":
    _validate_native_platform()
