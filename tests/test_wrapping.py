import pytest

from model_audit_lite.probes.behaviors import load_behaviors
from model_audit_lite.probes.wrapping import build_probes, load_wrappers
from model_audit_lite.probes.runner import run_probes

HARMBENCH_CSV = "Behavior,FunctionalCategory,BehaviorID\nDo benign thing one,standard,b1\nDo benign thing two,standard,b2\n"
JBB_CSV = "Index,Goal,Category\n0,First goal,x\n1,Second goal,y\n"
WRAPPERS_YAML = """
- id: pretext-x
  category: pretext-exercise
  user_template: "For a test: {behavior}"
- id: prefill-x
  category: prefill-injection
  user_template: "{behavior}"
  assistant_prefill: "Sure:"
"""


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_load_behaviors_detects_harmbench_and_jbb_columns(tmp_path):
    assert load_behaviors(_write(tmp_path, "hb.csv", HARMBENCH_CSV)) == ["Do benign thing one", "Do benign thing two"]
    assert load_behaviors(_write(tmp_path, "jbb.csv", JBB_CSV)) == ["First goal", "Second goal"]


def test_load_behaviors_limit(tmp_path):
    assert load_behaviors(_write(tmp_path, "hb.csv", HARMBENCH_CSV), limit=1) == ["Do benign thing one"]


def test_load_behaviors_rejects_unknown_columns(tmp_path):
    with pytest.raises(ValueError):
        load_behaviors(_write(tmp_path, "bad.csv", "foo,bar\n1,2\n"))


def test_build_probes_cross_product_and_prefill(tmp_path):
    behaviors = load_behaviors(_write(tmp_path, "hb.csv", HARMBENCH_CSV))
    wrappers = load_wrappers(_write(tmp_path, "w.yaml", WRAPPERS_YAML))
    probes = build_probes(behaviors, wrappers)
    assert len(probes) == 4  # 2 wrappers x 2 behaviors
    pretext = next(p for p in probes if p["id"] == "pretext-x::0")
    assert pretext["prompt"] == "For a test: Do benign thing one"
    assert pretext["assistant_prefill"] == ""
    prefill = next(p for p in probes if p["id"] == "prefill-x::1")
    assert prefill["prompt"] == "Do benign thing two" and prefill["assistant_prefill"] == "Sure:"


def test_load_wrappers_requires_fields(tmp_path):
    with pytest.raises(ValueError):
        load_wrappers(_write(tmp_path, "w.yaml", "- id: x\n  category: y\n"))  # missing user_template


def test_run_probes_passes_prefill_to_generate_fn(tmp_path):
    behaviors = load_behaviors(_write(tmp_path, "hb.csv", HARMBENCH_CSV))
    probes = build_probes(behaviors, load_wrappers(_write(tmp_path, "w.yaml", WRAPPERS_YAML)))
    seen = []

    def fake_generate(prompt, prefill=""):
        seen.append((prompt, prefill))
        return "I cannot help with that."  # refusal -> heuristic_safe

    report = run_probes(fake_generate, prompts=probes)
    assert report.total == 4 and report.safe_count == 4
    assert ("Do benign thing two", "Sure:") in seen
