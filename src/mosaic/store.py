"""One run owns its paths, immutable artifacts and hash-chained stage receipts."""
from __future__ import annotations

import json
import os
import copy
from pathlib import Path
import tempfile
import hashlib
import time
from functools import wraps
from threading import RLock

from mosaic.protocol.io import digest, read_json


def atomic_json(path, value):
    payload = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    atomic_bytes(path, payload)


def atomic_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".mosaic-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(.01 * 2 ** attempt)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def synchronized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


class RunStore:
    """Persist one request; changed requests cannot silently resume an old run."""
    def __init__(self, directory, request):
        self._lock = RLock()
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        request = copy.deepcopy(request)
        self.request = request
        self.request_hash = digest(request)
        self.manifest_path = self.root / "manifest.json"
        if self.manifest_path.exists():
            self.manifest = read_json(self.manifest_path)
            if self.manifest.get("request_sha256") != self.request_hash:
                raise ValueError("Run request changed; use a new output directory")
            self.verify()
        else:
            self.manifest = {"schema": "mosaic.run/1", "request": request,
                             "request_sha256": self.request_hash, "status": "running", "events": []}
            atomic_json(self.manifest_path, self.manifest)

    def _path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.manifest_path:
            raise ValueError("Artifact path escapes the run or overwrites its manifest")
        return path

    @synchronized
    def verify(self):
        if digest(self.manifest["request"]) != self.manifest.get("request_sha256"):
            raise ValueError("Stored run request was modified")
        previous = None
        for event in self.manifest["events"]:
            unsigned = {k: v for k, v in event.items() if k != "event_sha256"}
            if event.get("previous_sha256") != previous or digest(unsigned) != event.get("event_sha256"):
                raise ValueError("Run event chain was modified")
            path = self._path(event["artifact"])
            if not path.is_file() or digest(path.read_bytes()) != event["artifact_sha256"]:
                raise ValueError("Run artifact missing or modified: " + event["artifact"])
            previous = event["event_sha256"]
        if "result" in self.manifest:
            completions = [e for e in self.manifest["events"] if e["stage"] == "run/result"]
            if not completions:
                raise ValueError("Run result has no immutable receipt")
            saved = read_json(self._path(completions[-1]["artifact"]))
            if saved != {"status": self.manifest["status"], "result": self.manifest["result"]}:
                raise ValueError("Run result was modified")
        return True

    @synchronized
    def find(self, stage, input_value):
        key = digest(input_value)
        for event in reversed(self.manifest["events"]):
            if event["stage"] == stage and event["input_sha256"] == key:
                path = self._path(event["artifact"])
                if digest(path.read_bytes()) != event["artifact_sha256"]:
                    raise ValueError("Cached artifact was modified")
                return read_json(path), event
        return None

    @synchronized
    def save(self, stage, input_value, output, *, engine, model=None, usage=None):
        # No credentials, prompts with configuration, or mutable global output paths.
        index = len(self.manifest["events"])
        relative = f"artifacts/{index:05d}_{digest(stage)[:8]}.json"
        path = self._path(relative)
        atomic_json(path, output)
        event = {"stage": stage, "input_sha256": digest(input_value), "artifact": relative,
                 "artifact_sha256": digest(path.read_bytes()), "engine": engine,
                 "model": model, "usage": usage or {},
                 "previous_sha256": self.manifest["events"][-1]["event_sha256"] if index else None}
        event["event_sha256"] = digest(event)
        self.manifest["events"].append(event)
        atomic_json(self.manifest_path, self.manifest)
        return output

    @synchronized
    def track_file(self, stage, relative):
        path = self._path(relative)
        checksum = file_digest(path)
        if any(e["stage"] == stage and e["artifact"] == relative and e["artifact_sha256"] == checksum
               for e in self.manifest["events"]):
            return
        event = {"stage": stage, "input_sha256": self.request_hash, "artifact": relative,
                 "artifact_sha256": checksum, "engine": "program", "model": None, "usage": {},
                 "previous_sha256": self.manifest["events"][-1]["event_sha256"] if self.manifest["events"] else None}
        event["event_sha256"] = digest(event)
        self.manifest["events"].append(event)
        atomic_json(self.manifest_path, self.manifest)

    @synchronized
    def finish(self, status, result):
        if status not in ("complete", "partial", "failed"):
            raise ValueError("Invalid run status")
        self.manifest.update(status=status, result=result)
        self.save("run/result", self.request_hash, {"status": status, "result": result}, engine="program")
