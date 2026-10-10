"""Read ``tokenizer.chat_template`` out of a GGUF file's metadata.

GGUF repos carry the chat template *inside* the weights file, not as ``chat_template.jinja``, so a file-level
comparison cannot see it. This reads only the metadata block (via HTTP range requests for remote files, so the
multi-GB tensor data is never downloaded) and returns the template string, or None if the file has none.
"""
from __future__ import annotations

import struct

_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_STRING, _ARRAY = 8, 9
KEY = "tokenizer.chat_template"


class _Reader:
    """Sequential reader over either bytes or a ranged fetch function (offset, length) -> bytes."""

    def __init__(self, fetch, block: int = 4 << 20):
        self.fetch, self.block, self.pos = fetch, block, 0
        self._buf, self._buf_start = b"", 0

    def read(self, n: int) -> bytes:
        end = self.pos + n
        if not (self._buf_start <= self.pos and end <= self._buf_start + len(self._buf)):
            self._buf_start = self.pos
            self._buf = self.fetch(self.pos, max(n, self.block))
            if len(self._buf) < n:
                raise EOFError("GGUF metadata truncated")
        out = self._buf[self.pos - self._buf_start: end - self._buf_start]
        self.pos = end
        return out

    def u32(self): return struct.unpack("<I", self.read(4))[0]
    def u64(self): return struct.unpack("<Q", self.read(8))[0]
    def string(self): return self.read(self.u64()).decode("utf-8", errors="replace")


def _skip_value(r: _Reader, vtype: int) -> None:
    if vtype in _SCALAR:
        r.read(struct.calcsize(_SCALAR[vtype]))
    elif vtype == _STRING:
        n = r.u64()
        r.pos += n                            # skip without fetching the string body
    elif vtype == _ARRAY:
        et, n = r.u32(), r.u64()
        if et in _SCALAR:
            r.pos += n * struct.calcsize(_SCALAR[et])
        else:
            for _ in range(n):
                _skip_value(r, et)
    else:
        raise ValueError(f"unknown GGUF value type {vtype}")


def read_chat_template(fetch) -> str | None:
    r = _Reader(fetch)
    if r.read(4) != b"GGUF":
        raise ValueError("not a GGUF file")
    r.u32()                                    # version
    r.u64()                                    # tensor count
    for _ in range(r.u64()):
        key, vtype = r.string(), r.u32()
        if key == KEY and vtype == _STRING:
            return r.string()
        _skip_value(r, vtype)
    return None


def read_chat_template_from_hub(repo_id: str, filename: str) -> str | None:
    from huggingface_hub import hf_hub_url
    from huggingface_hub.utils import build_hf_headers, get_session

    url, headers = hf_hub_url(repo_id, filename), build_hf_headers()

    def fetch(offset: int, length: int) -> bytes:
        h = dict(headers, Range=f"bytes={offset}-{offset + length - 1}")
        resp = get_session().get(url, headers=h, timeout=60, follow_redirects=True) if _supports_follow() else get_session().get(url, headers=h, timeout=60)
        resp.raise_for_status()
        return resp.content

    return read_chat_template(fetch)


def _supports_follow() -> bool:
    import inspect
    from huggingface_hub.utils import get_session
    try:
        return "follow_redirects" in inspect.signature(get_session().get).parameters
    except (TypeError, ValueError):
        return False
