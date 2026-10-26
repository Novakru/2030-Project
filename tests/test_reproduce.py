from protocol_risk.reproduce import inventory


def test_artifact_inventory_detects_added_missing_and_changed_files(tmp_path):
    folder = tmp_path / "data/xdl/positive"
    folder.mkdir(parents=True)
    first, second = folder / "first.xdl", folder / "second.xdl"
    first.write_text("original", encoding="utf-8")
    before = inventory(tmp_path)
    second.write_text("added", encoding="utf-8")
    assert set(inventory(tmp_path)) - set(before) == {"data/xdl/positive/second.xdl"}
    first.write_text("changed", encoding="utf-8")
    assert inventory(tmp_path)["data/xdl/positive/first.xdl"] != before["data/xdl/positive/first.xdl"]
    first.unlink()
    assert "data/xdl/positive/first.xdl" not in inventory(tmp_path)
