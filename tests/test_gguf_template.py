import struct

from model_audit_lite.audit.gguf_template import read_chat_template


def _s(x: str) -> bytes:
    b = x.encode()
    return struct.pack("<Q", len(b)) + b


def _gguf(kvs: list[bytes]) -> bytes:
    return b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs)) + b"".join(kvs) + b"\0" * 64


def _fetch(data):
    return lambda off, n: data[off: off + n]


def test_finds_template_after_arrays_and_scalars():
    toks = _s("tokenizer.ggml.tokens") + struct.pack("<I", 9) + struct.pack("<IQ", 8, 3) + _s("a") + _s("bb") + _s("ccc")
    scores = _s("tokenizer.ggml.scores") + struct.pack("<I", 9) + struct.pack("<IQ", 6, 3) + struct.pack("<fff", 1, 2, 3)
    arch = _s("general.architecture") + struct.pack("<I", 8) + _s("llama")
    n = _s("llama.block_count") + struct.pack("<II", 4, 32)
    tpl = _s("tokenizer.chat_template") + struct.pack("<I", 8) + _s("{{ messages }}")
    assert read_chat_template(_fetch(_gguf([arch, n, toks, scores, tpl]))) == "{{ messages }}"


def test_none_when_absent():
    assert read_chat_template(_fetch(_gguf([_s("general.architecture") + struct.pack("<I", 8) + _s("llama")]))) is None


def test_small_blocks_cross_boundaries():
    from model_audit_lite.audit import gguf_template as g
    tpl = _s("tokenizer.chat_template") + struct.pack("<I", 8) + _s("X" * 5000)
    data = _gguf([tpl])
    r = g._Reader(_fetch(data), block=16)
    assert r.read(4) == b"GGUF"
