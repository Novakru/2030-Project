"""Small deterministic file and provenance helpers."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value, algorithm="sha256") -> str:
    data = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.new(algorithm, data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(canonical(record) + "\n")


@lru_cache(maxsize=32)
def load_library(name):
    return yaml.safe_load((ROOT / "libraries" / name).read_text(encoding="utf-8"))
