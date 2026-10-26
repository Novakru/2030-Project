"""Native SDK regression tests without connecting to physical controllers."""
import pytest

from protocol_risk.io import ROOT
from protocol_risk.platform_validation import legacy_representation, normalize_diagnostics, offline_platform, origin_for


def test_wrapper_and_unit_bearing_aliases_preserve_the_procedure():
    xml = '<XDL><Synthesis><Procedure><Add amount="5 mL"/><Stir speed="300 RPM"/></Procedure></Synthesis></XDL>'
    output, edits = legacy_representation(xml)
    assert output.startswith('<Synthesis>') and 'volume="5 mL"' in output and 'stir_speed="300 RPM"' in output
    assert len(edits) == 3 and legacy_representation(output) == (output, [])


@pytest.mark.parametrize("amount", ["2 g", "all", "2 mmol", "unknown"])
def test_mass_and_unknown_amounts_are_not_invented_as_volumes(amount):
    xml = '<Synthesis><Procedure><Add amount="' + amount + '"/></Procedure></Synthesis>'
    assert legacy_representation(xml) == (xml, [])


def test_ambiguous_wrappers_and_dual_attributes_are_not_overwritten():
    xml = '<XDL><Synthesis/><Synthesis/></XDL>'
    assert legacy_representation(xml) == (xml, [])
    xml = '<Synthesis><Procedure><Add amount="5 mL" volume="3 mL"/></Procedure></Synthesis>'
    assert legacy_representation(xml) == (xml, [])


def test_generated_async_ids_are_stable_unique_and_preserve_explicit_waits():
    xml = '<Synthesis><Procedure><Async pid="original"><Wait time="1 s"/></Async><Await pid="original"/><Async><Wait time="2 s"/></Async><Async><Wait time="3 s"/></Async></Procedure></Synthesis>'
    first, edits = legacy_representation(xml)
    assert legacy_representation(xml) == (first, edits)
    assert legacy_representation(first) == (first, [])
    assert '<Async pid="original">' in first and '<Await pid="original"/>' in first
    assert len(edits) == 2 and edits[0]["after"] != edits[1]["after"]
    assert all(e["kind"] == "deterministic_missing_async_pid" for e in edits)


def test_source_origin_can_be_recovered_only_from_exact_archive_members():
    parent = {"id": "repaired", "raw_xdl_path": "data/raw/native/a.xdl", "raw_sha256": "original", "source": {"doi": "fixture"}}
    member = {"path": parent["raw_xdl_path"], "sha256": "original"}
    assert origin_for(parent, {}, [member])["resources"] == [member]
    with pytest.raises(ValueError, match="cannot be reconstructed"):
        origin_for(parent, {}, [dict(member, sha256="changed")])


def test_log_normalization_removes_clock_and_addresses_but_preserves_warning():
    assert normalize_diagnostics('2026-10-26 11:17:54,897 ; pump ; Warning 0xabc123\n') == 'pump ; Warning <address>\n'


@pytest.fixture(scope="module")
def sdk():
    if not (ROOT / "data/platform_sources.lock.json").exists():
        pytest.skip("Original native SDK sources are not installed")
    pytest.importorskip("networkx")
    pytest.importorskip("serial")
    with offline_platform() as value:
        yield value


def test_native_sdk_rejects_bad_units_and_undeclared_vessels(sdk):
    XDL, _ = sdk
    xml = '<Synthesis><Hardware><Component id="r" type="reactor"/></Hardware><Reagents><Reagent name="water"/></Reagents><Procedure><Add vessel="r" reagent="water" volume="1 mL"/></Procedure></Synthesis>'
    assert len(XDL(xml, logging_level=50).steps) == 1
    with pytest.raises(Exception):
        XDL(xml.replace('volume="1 mL"', 'volume="not_a_volume"'), logging_level=50)
    with pytest.raises(Exception):
        XDL(xml.replace('vessel="r"', 'vessel="missing"'), logging_level=50)


def test_native_compiler_guard_rejects_device_io_and_physical_controller_mode(sdk):
    XDL, calls = sdk
    import socket
    import serial
    from chempiler import Chempiler
    with pytest.raises(RuntimeError, match="I/O is disabled"):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(RuntimeError, match="I/O is disabled"):
        serial.Serial(port="COM999")
    with pytest.raises(RuntimeError, match="Physical controller"):
        Chempiler(experiment_code="test", graph_file={}, output_dir="", simulation=False, device_modules=[])
    assert calls["blocked_io_attempts"] >= 2
