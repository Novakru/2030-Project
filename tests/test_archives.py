import io
import re
import zipfile

import pytest

from protocol_risk.archives import HTTPRangeReader


class Response:
    def __init__(self, content, start, end, total):
        self.content = content[start:end + 1]
        self.status_code = 206
        self.headers = {"Content-Range": f"bytes {start}-{end}/{total}"}

    def close(self):
        pass


class Session:
    def __init__(self, content):
        self.content = content

    def get(self, url, headers, **kwargs):
        start, end = map(int, re.fullmatch(r"bytes=(\d+)-(\d+)", headers["Range"]).groups())
        return Response(self.content, start, end, len(self.content))


def test_remote_zip_read_seeks_and_validates_crc():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("procedures/one.xdl", "<Synthesis/>")
        archive.writestr("large.bin", b"x" * 100000)
    content = buffer.getvalue()
    reader = HTTPRangeReader("https://example.invalid/archive.zip", len(content), Session(content), block_size=64)
    with zipfile.ZipFile(reader) as archive:
        assert archive.read("procedures/one.xdl") == b"<Synthesis/>"
    assert reader.bytes_downloaded <= len(content) * 3


def test_ignored_range_is_rejected_without_reading_a_large_body():
    class Broken:
        def get(self, *args, **kwargs):
            response = Response(b"hello", 0, 4, 5)
            response.status_code = 200
            return response
    reader = HTTPRangeReader("https://example.invalid/large.zip", 5, Broken())
    with pytest.raises(ValueError, match="refusing a full download"):
        reader.read(1)


def test_read_spanning_cache_boundary_matches_a_real_seekable_file():
    content = bytes(range(256)) * 100
    reader = HTTPRangeReader("https://example.invalid/file", len(content), Session(content), block_size=64)
    reader.seek(1)
    assert reader.read(8192) == content[1:8193]
