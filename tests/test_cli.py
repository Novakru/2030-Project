import pytest

from protocol_risk.cli import main


def test_ingest_list_result_does_not_fail_after_writing_the_archive(monkeypatch):
    monkeypatch.setattr("protocol_risk.ingest.ingest", lambda: [{"reactions": 1}])
    assert main(["ingest"]) == 0


@pytest.mark.parametrize("passed,exit_code", [(True, 0), (False, 1)])
def test_publication_audit_exit_code_reports_failure(monkeypatch, passed, exit_code):
    monkeypatch.setattr("protocol_risk.publications.audit_publications", lambda: {"passed": passed})
    assert main(["audit-publications"]) == exit_code
