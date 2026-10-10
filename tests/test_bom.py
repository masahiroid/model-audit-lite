import datetime

from model_audit_lite.audit.bom import build_bom, detect_formats, merge_into
from model_audit_lite.audit.conversion import ChatTemplateDiff, ProbeDiff, ProbeRegression

AUDIT = {
    "repo_id": "me/model-mlx-4bit",
    "total_files": 5,
    "risky_pickle_files": ["pytorch_model.bin"],
    "custom_code_files": ["modeling.py"],
    "checksums": {"model.safetensors": "a" * 64, "modeling.py": "b" * 64},
}
NOW = datetime.datetime(2026, 10, 3, tzinfo=datetime.timezone.utc)


def test_standalone_bom_structure():
    bom = build_bom(AUDIT, revision="abc", license_id="apache-2.0", tags=["mlx"], now=NOW)
    assert bom["bomFormat"] == "CycloneDX" and bom["specVersion"] == "1.6"
    c = bom["components"][0]
    assert c["type"] == "machine-learning-model" and c["version"] == "abc"
    assert [x["name"] for x in c["components"]] == ["model.safetensors", "modeling.py"]
    assert c["components"][0]["hashes"] == [{"alg": "SHA-256", "content": "a" * 64}]
    props = {(p["name"], p["value"]) for p in c["properties"]}
    assert ("model-audit-lite:risky-pickle-file", "pytorch_model.bin") in props
    assert ("model-audit-lite:formats", "safetensors,pytorch-pickle,mlx") in props
    assert "pedigree" not in c


def test_lineage_and_probe_regressions():
    td = ChatTemplateDiff("base/x", "me/model-mlx-4bit", "t", "t", False)
    pd = ProbeDiff(items=[
        ProbeRegression("p1", "c", True, False, "ok", "bad"),
        ProbeRegression("p2", "c", False, True, "bad", "ok"),
    ])
    bom = build_bom(AUDIT, base_repo_id="base/x", base_revision="r1", template_diff=td, probe_diff=pd, probe_total=60, now=NOW)
    c = bom["components"][0]
    assert c["pedigree"]["ancestors"][0]["bom-ref"] == "hf:base/x@r1"
    props = {p["name"]: p["value"] for p in c["properties"]}
    assert props["model-audit-lite:chat-template-changed"] == "false"
    assert props["model-audit-lite:probe-regressions"] == "1"
    assert props["model-audit-lite:probe-regression-ids"] == "p1"


def test_merge_keeps_existing_and_adds_ours():
    existing = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [
        {"type": "machine-learning-model", "name": "me/model-mlx-4bit", "modelCard": {"x": 1}, "properties": [{"name": "k", "value": "v"}]}]}
    ours = build_bom(AUDIT, base_repo_id="base/x", now=NOW)
    merged = merge_into(existing, ours)
    c = merged["components"][0]
    assert c["modelCard"] == {"x": 1} and {"name": "k", "value": "v"} in c["properties"]
    assert c["pedigree"]["ancestors"][0]["name"] == "base/x"
    assert len(c["components"]) == 2
    assert len(merge_into(merged, ours)["components"][0]["components"]) == 2  # idempotent for files


def test_detect_formats():
    assert detect_formats(["a.gguf", "b.mlpackage/Data/x"]) == ["gguf", "coreml"]


def test_coreml_weight_blob_is_not_detected_as_pickle():
    fmts = detect_formats(["m.mlpackage/Data/com.apple.CoreML/weights/weight.bin", "m.mlpackage/Manifest.json"])
    assert "pytorch-pickle" not in fmts and "coreml" in fmts
