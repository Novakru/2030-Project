import pytest

from protocol_risk.api import Client, settings


class Reply:
    status_code = 200

    def __init__(self, content):
        self.content = content

    def json(self):
        return {"choices": [{"message": {"content": self.content}}], "model": "stub"}


def test_api_response_cannot_echo_credentials(monkeypatch):
    client = Client({"api_key": "secret-test-only", "base_url": "https://example.invalid/v1", "model": "stub"})
    monkeypatch.setattr(client, "request", lambda messages: Reply('{"api_key":"secret-test-only"}'))
    with pytest.raises(ValueError, match="credentials"):
        client.complete("system", "prompt", cache=False)


def test_gateway_minimal_request_does_not_include_unsupported_options(monkeypatch):
    client = Client({"api_key": "test-only", "base_url": "https://example.invalid/v1", "model": "stub"})
    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return Reply('{"ok":true}')

    monkeypatch.setattr("protocol_risk.api.requests.post", post)
    client.complete("system", "prompt", cache=False)
    assert set(captured["json"]) == {"model", "messages"}
    assert captured["headers"]["Authorization"] == "Bearer test-only"


def test_embedded_credentials_are_not_allowed_in_logged_base_url(tmp_path, monkeypatch):
    for key in ("API_KEY", "BASE_URL", "MODEL"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("api_key=test-only\nbase_url=https://user:password@example.invalid/v1\nmodel=stub\n", encoding="utf-8")
    with pytest.raises(ValueError, match="embedded credentials"):
        settings(path)
