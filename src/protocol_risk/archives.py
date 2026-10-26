"""Read public ZIP members by verified HTTP byte ranges without downloading videos/NMR archives."""
from __future__ import annotations

import io
from collections import OrderedDict

import requests


class HTTPRangeReader(io.BufferedIOBase):
    def __init__(self, url, size, session=None, block_size=131072, max_read=16777216):
        self.url, self.size = url, size
        self.session = session or requests.Session()
        self._own_session = session is None
        self.block_size, self.max_read = block_size, max_read
        self.position, self.bytes_downloaded, self.requests_made = 0, 0, 0
        self.blocks = OrderedDict()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = offset if whence == io.SEEK_SET else self.position + offset if whence == io.SEEK_CUR else self.size + offset
        if position < 0:
            raise OSError("Negative archive position")
        self.position = position
        return position

    def _fetch(self, start, end):
        response = self.session.get(self.url, headers={"Range": f"bytes={start}-{end}"}, timeout=45, stream=True)
        try:
            expected = f"bytes {start}-{end}/{self.size}"
            if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server did not return the requested archive range; refusing a full download")
            content = response.content
            if len(content) != end - start + 1:
                raise ValueError("Truncated archive range")
        finally:
            response.close()
        self.requests_made += 1
        self.bytes_downloaded += len(content)
        for position in range(start, end + 1, self.block_size):
            self.blocks[position] = content[position - start:position - start + self.block_size]

    def read(self, size=-1):
        size = self.size - self.position if size < 0 else min(size, self.size - self.position)
        if size <= 0:
            return b""
        if size > self.max_read:
            raise ValueError("Archive read exceeds the configured per-read limit")
        first = self.position // self.block_size * self.block_size
        last = (self.position + size - 1) // self.block_size * self.block_size
        missing = [offset for offset in range(first, last + 1, self.block_size) if offset not in self.blocks]
        if missing:
            self._fetch(missing[0], min(missing[-1] + self.block_size, self.size) - 1)
        content = b"".join(self.blocks[offset] for offset in range(first, last + 1, self.block_size))
        # Evict only after assembling this read, which may straddle 129 blocks.
        while len(self.blocks) > 128:
            self.blocks.popitem(last=False)
        begin = self.position - first
        self.position += size
        return content[begin:begin + size]

    def close(self):
        if self._own_session:
            self.session.close()
        super().close()
