"""Verify deterministic artifact rebuilding while HTTP access is disabled."""
from __future__ import annotations

import platform
import site
import sys
from pathlib import Path
from unittest.mock import patch

from .io import ROOT, digest, write_json


def inventory(root):
    files = [root / name for name in (
        "data/positives.jsonl", "data/negatives.jsonl", "data/raw/selected.jsonl",
        "data/controls/parents.jsonl", "data/controls/negatives.jsonl", "data/unmapped.jsonl",
        "data/intermediate/rejected.jsonl", "data/publications/candidates.jsonl",
        "data/publications/quarantined.jsonl", "data/hte/contrasts.jsonl", "reports/stats.json",
        "reports/publication_candidates.json", "reports/hte_contrasts.json", "data/native_negatives.jsonl",
        "reports/native_negatives.json", "data/dataset.json", "reports/dataset_coverage.json",
        "data/sop/parents.jsonl", "data/sop/negatives.jsonl", "reports/sop_dataset.json",
        "data/publications/platform_validation.jsonl", "data/publications/platform_positives.jsonl", "reports/native_platform.json")]
    for name, pattern in (("data/xdl", "*.xdl"), ("data/controls/xdl", "*.xdl"), ("data/raw/protocols", "*.json")):
        files.extend((root / name).rglob(pattern))
    files.extend((root / "data/compiled/publication").glob("*.xdlexe"))
    return {path.relative_to(root).as_posix(): digest(path.read_bytes())
            for path in sorted(set(files)) if path.is_file()}


def verify_rebuild(limit=140, per_risk=12):
    from .pipeline import build
    from .publications import prepare_publication_candidates
    before = inventory(ROOT)
    attempted = 0

    def deny_http(*args, **kwargs):
        nonlocal attempted
        attempted += 1
        raise RuntimeError("HTTP access attempted during an offline rebuild")

    with patch("requests.sessions.Session.request", deny_http):
        build(limit, per_risk)
        if (ROOT / "data/publications/members.lock.json").exists():
            prepare_publication_candidates()
            if (ROOT / "data/native_negatives.jsonl").exists():
                from .native import build_native_negatives
                build_native_negatives(per_risk)
            if (ROOT / "data/publications/platform_validation.jsonl").exists():
                from .platform_validation import validate_native_platform
                validate_native_platform()
        if (ROOT / "data/hte/contrasts.jsonl").exists():
            from .contrasts import build_contrasts
            build_contrasts()
        if (ROOT / "data/sop/negatives.jsonl").exists():
            from .sop import build_sop
            build_sop()
        if (ROOT / "data/dataset.json").exists():
            from .report import report
            report()
    after = inventory(ROOT)
    changed = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    external = [p for p in sys.path if "site-packages" in p.lower() and not Path(p).resolve().is_relative_to(Path(sys.prefix).resolve())]
    inputs = [ROOT / "requirements.lock.txt", ROOT / "data/sources.lock.json", ROOT / "data/raw/reactions.parquet",
              ROOT / "data/sop_sources.lock.json"]
    inputs.extend(ROOT / name for name in ("requirements-platform.lock.txt", "data/platform_sources.lock.json"))
    inputs.extend(ROOT / name for name in ("data/publications.lock.json", "data/publications/members.lock.json", "data/publications/chemputer_2022.jsonl"))
    for folder, pattern in (("src", "*.py"), ("libraries", "*.yaml"), ("schemas", "*.xsd"),
                            ("data/intermediate/extractions", "*.json"), ("data/reviews", "*.json"),
                            ("data/upstream/sop", "*"), ("data/intermediate/sop_text", "*.txt")):
        inputs.extend((ROOT / folder).rglob(pattern))
    if (ROOT / "data/platform_sources.lock.json").exists():
        from .io import read_json
        inputs.extend(ROOT / m["path"] for m in read_json(ROOT / "data/platform_sources.lock.json")["members"])
    result = {"passed": bool(before) and not changed and attempted == 0,
              "files_compared": len(after), "before_sha256": digest(before), "after_sha256": digest(after),
              "byte_identical": bool(before) and not changed, "changed": changed,
              "http_requests_blocked_during_rebuild": True, "http_requests_attempted": attempted,
              "inputs_sha256": digest({p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(inputs) if p.is_file()}),
              "python_version": platform.python_version(), "user_site_enabled": site.ENABLE_USER_SITE,
              "external_site_packages": external}
    write_json(ROOT / "reports/reproducibility.json", result)
    return result
