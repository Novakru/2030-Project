"""Collect the original compiler source bundled with the Science 2022 dataset."""
import binascii
from pathlib import PurePosixPath
import zipfile

from protocol_risk.archives import HTTPRangeReader
from protocol_risk.io import ROOT, digest, read_json, write_json


PACKAGES = {
    "xdl_old/xdl-master/": "xdl",
    "chemputerxdl_old/chemputerxdl/": "chemputerxdl",
    "chempiler_old/chempiler-master/": "chempiler",
    "chemputerapi_old/chemputerapi-master/": "chemputerapi",
    "commanduino_old/commanduino/": "commanduino",
    "commanduinolabware_old/commanduinolabware/": "commanduinolabware",
    "seriallabware-SerialLabware2_old/seriallabware-SerialLabware2/": "seriallabware",
}


def collect():
    archive = read_json(ROOT / "data/publications.lock.json")["records"][0]["archives"][1]
    members = []
    with HTTPRangeReader(archive["url"], archive["size"]) as remote:
        with zipfile.ZipFile(remote) as source:
            selected = []
            for info in source.infolist():
                for prefix, package in PACKAGES.items():
                    marker = "SI files/Software/" + prefix
                    if info.filename.startswith(marker) and not info.is_dir():
                        relative = PurePosixPath(info.filename[len(marker):])
                        if (any(p in ("..", ".git", "__pycache__", ".vscode") for p in relative.parts)
                                or relative.suffix in (".pyc", ".mp4", ".exe", ".pdf", ".zip") or info.file_size > 2097152):
                            continue
                        selected.append((info, package, relative))
            start = min(i.header_offset for i, _, _ in selected)
            finish = max(i.header_offset + i.compress_size + 4096 for i, _, _ in selected)
            if finish - start < remote.max_read:
                remote.seek(start)
                remote.read(finish - start)  # Reuse adjacent compressed source members in the range cache.
            for info, package, relative in selected:
                folder = (ROOT / "data/upstream/platform_2022" / package).resolve()
                target = (folder / str(relative)).resolve()
                if not target.is_relative_to(folder) or any(c in relative.name for c in '<>:"|?*'):
                    raise ValueError("Unsafe archive source path")
                blob = target.read_bytes() if target.exists() else b""
                if not target.exists() or len(blob) != info.file_size or binascii.crc32(blob) & 0xffffffff != info.CRC:
                    blob = source.read(info)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(blob)
                members.append({"path": target.relative_to(ROOT).as_posix(), "archive_member": info.filename,
                                "package": package, "sha256": digest(blob), "crc32": info.CRC, "size": len(blob)})
        result = {"source_doi": "10.5281/zenodo.6534009", "archive_url": archive["url"],
                  "archive_publisher_checksum": archive["checksum"], "full_archive_checksum_verified": False,
                  "member_integrity": "ZIP CRC32 and frozen member SHA256", "members": members,
                  "http_bytes_downloaded": remote.bytes_downloaded, "http_range_requests": remote.requests_made}
    write_json(ROOT / "data/platform_sources.lock.json", result)
    print({"source_files": len(members), "http_bytes_downloaded": result["http_bytes_downloaded"]})


if __name__ == "__main__":
    collect()
