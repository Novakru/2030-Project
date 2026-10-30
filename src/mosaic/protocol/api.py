"""OpenAI-compatible HTTP client; credentials never enter logs or artifacts."""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit
from pathlib import Path

import requests

from .io import ROOT, digest, read_json, write_json


def settings(env_file=None):
    values = {}
    path = Path(env_file) if env_file else ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][\w]*)\s*=\s*(.*)", line)
            if match:
                name, value = match.groups()
                value = value.strip()
                if value[:1] in ("'", '"') and value[-1:] == value[:1]:
                    value = value[1:-1]
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0]
                values[name.lower()] = value
    for name in ("api_key", "base_url", "model"):
        values[name] = os.environ.get(name.upper(), values.get(name, ""))
        if not values[name]:
            raise ValueError(f"Missing configuration field: {name}")
    address = urlsplit(values["base_url"])
    if address.scheme not in ("http", "https") or not address.netloc or address.username or address.password or address.query or address.fragment:
        raise ValueError("base_url must be an HTTP(S) service URL without embedded credentials, query or fragment")
    return {k: values[k] for k in ("api_key", "base_url", "model")}


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text)


class Client:
    def __init__(self, config=None, timeout=120, retries=3):
        self.config = config or settings()
        self.timeout = timeout
        self.retries = retries
        self.deadline = None
        self.transport_attempts = 0
        base = self.config["base_url"].rstrip("/")
        self.endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"

    def request(self, messages, *, key=None):
        # Some gateways reject max_tokens / temperature. Use the minimal protocol.
        body = {"model": self.config["model"], "messages": messages}
        for attempt in range(self.retries):
            remaining = self.deadline - time.monotonic() if self.deadline is not None else self.timeout
            if remaining <= 0:
                raise RuntimeError("API wall-clock budget exhausted")
            self.transport_attempts += 1
            try:
                response = requests.post(
                    self.endpoint, json=body,
                    headers={"Authorization": "Bearer " + (key or self.config["api_key"])},
                    timeout=min(self.timeout, remaining),
                )
            except requests.RequestException as error:
                if attempt + 1 == self.retries:
                    raise RuntimeError(f"API transport failed: {type(error).__name__}") from None
                time.sleep(2 ** attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt + 1 < self.retries:
                time.sleep(2 ** attempt)
                continue
            return response
        raise RuntimeError("Unreachable API retry state")

    def complete(self, system, prompt, cache=True):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        cache_key = digest({"model": self.config["model"], "endpoint": self.endpoint, "messages": messages})
        path = ROOT / "outputs/cache/api" / (cache_key + ".json")
        if cache and path.exists():
            return {**read_json(path), "cache_hit": True}
        response = self.request(messages)
        if response.status_code != 200:
            raise RuntimeError(f"API HTTP {response.status_code}; response body omitted to protect credentials")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        if self.config["api_key"] in content:
            raise ValueError("Rejected response containing credentials")
        try:
            parsed = parse_json(content)
        except (ValueError, TypeError):
            parsed = {"invalid_json_text": content}
        result = {"data": parsed, "model": data.get("model"),
                  "usage": data.get("usage", {}), "cache_key": cache_key}
        result["transport_attempts"] = self.transport_attempts
        if cache:
            write_json(path, result)
        return {**result, "cache_hit": False}


def probe(env_file=None):
    client = Client(settings(env_file), timeout=45, retries=2)
    nonce = secrets.token_hex(12)
    expected = {"status": "ok", "nonce": nonce}
    messages = [{"role": "user", "content": "Return only this JSON: " + json.dumps(expected)}]
    response = client.request(messages)
    report = {"endpoint": client.endpoint, "configured_model": client.config["model"],
              "http_status": response.status_code, "structured_response_valid": False}
    if response.status_code == 200:
        data = response.json()
        try:
            report["structured_response_valid"] = parse_json(data["choices"][0]["message"]["content"]) == expected
        except (KeyError, TypeError, ValueError):
            pass
        report["returned_model"] = data.get("model")
        report["usage"] = data.get("usage", {})
        invalid = client.request(messages, key="invalid-key-test-" + secrets.token_hex(16))
        report["invalid_key_http_status"] = invalid.status_code
        report["invalid_key_rejected"] = invalid.status_code in (401, 403)
    report["passed"] = (report["http_status"] == 200 and report["structured_response_valid"]
                        and report.get("invalid_key_rejected", False))
    report["identity_limit"] = "A gateway response cannot independently attest the upstream model identity."
    write_json(ROOT / "outputs/api_connectivity.json", report)
    return report
