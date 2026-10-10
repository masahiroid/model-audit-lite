import json

from model_audit_lite.audit.conversion import ChatTemplateDiff, ProbeDiff, ProbeRegression
from model_audit_lite.reporting.scan import assess, run_scan

CLEAN = {"repo_id": "me/m", "total_files": 3, "risky_pickle_files": [], "custom_code_files": [], "checksums": {"model.safetensors": "a" * 64}}


def test_clean_scan_passes_and_writes_three_files(tmp_path):
    s = run_scan(CLEAN, tmp_path, lang="en")
    assert s["status"] == "pass" and s["fail"] == []
    assert {p.name for p in tmp_path.iterdir()} == {"report.md", "bom.json", "summary.json"}
    assert json.loads((tmp_path / "bom.json").read_text())["bomFormat"] == "CycloneDX"
    assert "me/m" in (tmp_path / "report.md").read_text()


def test_pickle_fails_and_custom_code_warns():
    assert assess({**CLEAN, "risky_pickle_files": ["a.bin"]})["status"] == "fail"
    s = assess({**CLEAN, "custom_code_files": ["m.py"]})
    assert s["status"] == "warn" and s["warn"] == ["custom-code-files"]


def test_conversion_regression_fails(tmp_path):
    td = ChatTemplateDiff("base/x", "me/m", "a", "b", True)
    pd = ProbeDiff(items=[ProbeRegression(f"p{i}", "c", True, False, "ok", "bad") for i in range(9)])  # 9 regressions: significant
    s = run_scan(CLEAN, tmp_path, lang="en", base_repo_id="base/x", template_diff=td, probe_diff=pd, probe_total=60)
    assert s["status"] == "fail" and set(s["fail"]) == {"chat-template-changed", "probe-regressions"}
    bom = json.loads((tmp_path / "bom.json").read_text())
    assert bom["components"][0]["pedigree"]["ancestors"][0]["name"] == "base/x"
