"""OpenAI-compatible chat client for the ProcGraph agents.

* reads api_key / base_url / model from a .env file or environment variables
* tries ``response_format={"type":"json_object"}``; falls back automatically if the gateway rejects it
* retries transport errors / 429 / 5xx with exponential backoff
* content-addressed disk cache (same prompt -> same answer, free re-runs)
* ``replay`` mode: only cached answers, no network (offline regression tests)
* ``ScriptedLLM`` for unit tests
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path

import requests


def load_env(path=None):
    values = {}
    candidates = [Path(path)] if path else [Path.cwd() / ".env", Path.cwd() / "_env"]
    for p in candidates:
        if p.exists():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)", line)
                if m:
                    k, v = m.group(1).lower(), m.group(2).strip()
                    if v[:1] in "'\"" and v.rstrip()[-1:] == v[:1]:
                        v = v.strip()[1:-1]
                    values[k] = v.strip()
            break
    for k in ("api_key", "base_url", "model", "api", "reasoning_effort"):
        values[k] = os.environ.get(k.upper(), values.get(k, ""))
    return values


def parse_json_reply(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Take the outermost {...} block (models sometimes add a sentence).
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except ValueError:
            pass
    return {"_invalid_json": text[:20000]}


class LLMError(RuntimeError):
    pass


class LLM:
    # Reasoning effort per agent role; the extractor does the hard reading, the rest are checks.
    DEFAULT_EFFORT = {"extractor": "medium", "repairer": "medium", "critic": "low", "curator": "low", "ping": "low"}

    def __init__(self, env_file=None, model=None, cache_dir="outputs/pg_cache", mode="live", timeout=300,
                 retries=4, temperature=None, max_calls=None, api=None, effort=None):
        cfg = load_env(env_file)
        self.api_key, self.base_url = cfg.get("api_key", ""), cfg.get("base_url", "").rstrip("/")
        self.model = model or cfg.get("model", "")
        # api: "responses" (OpenAI Responses API), "chat" (chat/completions) or "auto" (responses, then chat)
        self.api = (api or cfg.get("api") or "auto").lower()
        self.effort = effort or cfg.get("reasoning_effort") or None
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.mode = mode  # live | replay | record (live + always write)
        self.timeout, self.retries, self.temperature = timeout, retries, temperature
        self.max_calls = max_calls
        self.json_mode = True
        self.usage = Counter()
        self.calls = Counter()
        self._lock = threading.Lock()
        self._endpoint = None
        if mode != "replay" and not (self.api_key and self.base_url and self.model):
            raise LLMError("api_key/base_url/model missing: set them in .env (see .env.example)")

    # ------------------------------------------------------------------ endpoint
    def _effort(self, role):
        return self.effort or self.DEFAULT_EFFORT.get(role, "medium")

    def _url(self, suffix):
        base = self.base_url
        for tail in ("/chat/completions", "/responses"):
            if base.endswith(tail):
                base = base[: -len(tail)]
        if not re.search(r"/v\d+$", base):
            base += "/v1"
        return base + suffix

    def _call(self, role, system, user):
        styles = {"responses": ["responses"], "chat": ["chat"]}.get(self.api, ["responses", "chat"])
        last = None
        for style in styles:
            try:
                out = self._post_responses(role, system, user) if style == "responses" else self._post_chat(system, user)
                if self.api == "auto":
                    self.api = style  # remember what works
                return out
            except _Unsupported as err:
                last = err
        raise LLMError(f"no supported API style: {last}")

    def _send(self, url, body):
        last = None
        for attempt in range(self.retries):
            started = time.monotonic()
            try:
                r = requests.post(url, json=body, timeout=self.timeout,
                                  headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"})
            except requests.RequestException as err:
                last = f"transport {type(err).__name__}"
                time.sleep(min(30, 2 ** attempt))
                continue
            if r.status_code in (408, 409, 425, 429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                time.sleep(min(60, 2 ** (attempt + 1)))
                continue
            return r, round(time.monotonic() - started, 2)
        raise LLMError(f"request failed after {self.retries} attempts: {last}")

    def _post_responses(self, role, system, user):
        body = {"model": self.model, "instructions": system, "input": user}
        effort = self._effort(role)
        if effort and effort != "none":
            body["reasoning"] = {"effort": effort}
        if self.json_mode:
            body["text"] = {"format": {"type": "json_object"}}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        r, elapsed = self._send(self._url("/responses"), body)
        if r.status_code in (404, 405):
            raise _Unsupported(f"/responses HTTP {r.status_code}")
        if r.status_code == 400 and ("text" in body or "reasoning" in body):
            # Gateways differ: drop optional features one at a time.
            if self.json_mode:
                self.json_mode = False
            elif self.effort != "none":
                self.effort = "none"
            else:
                raise LLMError(f"HTTP 400: {r.text[:300]}")
            return self._post_responses(role, system, user)
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        content = response_text(data)
        self._check(content)
        usage = data.get("usage") or {}
        return content, _flat_usage(usage), elapsed

    def _post_chat(self, system, user):
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        r, elapsed = self._send(self._url("/chat/completions"), body)
        if r.status_code in (404, 405):
            raise _Unsupported(f"/chat/completions HTTP {r.status_code}")
        if r.status_code == 400 and self.json_mode:
            self.json_mode = False
            return self._post_chat(system, user)
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        self._check(content)
        return content, _flat_usage(data.get("usage") or {}), elapsed

    def _check(self, content):
        if self.api_key and self.api_key in content:
            raise LLMError("response echoed the credential")

    def _key(self, role, system, user):
        blob = json.dumps([self.model, system, user, self.temperature, self._effort(role)], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]

    def complete(self, role, system, user, sample=0):
        key = self._key(role, system, user) + (f"_s{sample}" if sample else "")
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        if path and path.exists() and self.mode != "record":
            data = json.loads(path.read_text(encoding="utf-8"))
            with self._lock:
                self.calls[role + ":cached"] += 1
            return data["content"], data
        if self.mode == "replay":
            raise LLMError(f"replay mode: no cached response for {role} ({key})")
        with self._lock:
            live = sum(v for k, v in self.calls.items() if not k.endswith(":cached"))
            if self.max_calls is not None and live >= self.max_calls:
                raise LLMError("call budget exhausted")
            self.calls[role] += 1
        content, usage, elapsed = self._call(role, system, user)
        data = {"role": role, "model": self.model, "content": content, "usage": usage, "elapsed_s": elapsed,
                "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with self._lock:
            for k, v in (usage or {}).items():
                if isinstance(v, (int, float)):
                    self.usage[k] += v
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return content, data

    def json(self, role, system, user, sample=0):
        content, meta = self.complete(role, system, user, sample)
        return parse_json_reply(content), meta

class _Unsupported(Exception):
    pass


def response_text(data):
    """Equivalent of the SDK's ``response.output_text`` for a raw Responses API payload."""
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts = []
    for item in data.get("output") or []:
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") in ("output_text", "text") and isinstance(c.get("text"), str):
                    parts.append(c["text"])
    return "".join(parts)


def _flat_usage(usage):
    out = {}
    for k, v in usage.items():
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (int, float)):
                    out[f"{k}.{k2}"] = v2
    return out


class ScriptedLLM:
    """Deterministic stand-in for tests: returns queued replies per role."""

    def __init__(self, replies):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.calls = Counter()
        self.usage = Counter()
        self.model = "scripted"
        self.log = []

    def json(self, role, system, user, sample=0):
        self.calls[role] += 1
        self.log.append((role, user))
        queue = self.replies.get(role) or []
        if not queue:
            return ({"issues": []} if role == "critic" else {"_invalid_json": "no scripted reply"}), {}
        reply = queue.pop(0)
        return (reply(user) if callable(reply) else json.loads(json.dumps(reply))), {}
