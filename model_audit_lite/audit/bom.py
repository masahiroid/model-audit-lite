"""CycloneDX 1.6 ML-BOM output that bundles everything model-audit-lite knows about a model in one document.

Why in this tool: generic ML-BOM generators (OWASP AIBOM Generator, cdxgen, ...) describe a single model's metadata.
This adds what only an audit + comparison run knows, in standard fields, so it can stand alone or be merged into a
BOM produced elsewhere (``merge_into``):

- file checksums (SHA-256) as nested ``file`` components, plus pickle / custom-code findings as properties
- conversion lineage: ``pedigree.ancestors`` (the source repo) with the detected target format, chat-template
  equality and, if probes were run, safety-probe regressions
- the audit tool itself under ``metadata.tools``

Pure functions over the dicts / dataclasses the other modules return, so no network is needed to test them.
"""
from __future__ import annotations

import datetime
import json
import uuid

from .. import __version__

NS = "model-audit-lite"  # property-name prefix

# file-extension -> format label (first match wins)
_FORMATS = [
    (".gguf", "gguf"),
    (".mlpackage", "coreml"),
    (".mlmodel", "coreml"),
    (".mlmodelc", "coreml"),
    (".onnx", "onnx"),
    (".tflite", "tflite"),
    (".safetensors", "safetensors"),
    (".bin", "pytorch-pickle"),
    (".pt", "pytorch-pickle"),
    (".pth", "pytorch-pickle"),
]

from .files import _COREML_BLOB  # noqa: E402


def detect_formats(filenames: list[str], tags: list[str] | None = None) -> list[str]:
    # Core ML raw weight blobs (weights/weight.bin) are not pickle: keep them out of format detection.
    filenames = [f for f in filenames if not _COREML_BLOB.search(f)]
    found: list[str] = []
    for ext, label in _FORMATS:
        if any(f.endswith(ext) or f".{ext.lstrip('.')}/" in f for f in filenames) and label not in found:
            found.append(label)
    tags = [t.lower() for t in (tags or [])]
    if "mlx" in tags and "mlx" not in found:
        found.append("mlx")
    return found


def _prop(name: str, value) -> dict:
    return {"name": f"{NS}:{name}", "value": str(value)}


def _repo_component(repo_id: str, revision: str | None = None) -> dict:
    c = {
        "type": "machine-learning-model",
        "bom-ref": f"hf:{repo_id}" + (f"@{revision}" if revision else ""),
        "name": repo_id,
        "externalReferences": [{"type": "distribution", "url": f"https://huggingface.co/{repo_id}"}],
    }
    if revision:
        c["version"] = revision
    return c


def build_bom(
    audit_result: dict,
    *,
    base_repo_id: str | None = None,
    base_revision: str | None = None,
    revision: str | None = None,
    license_id: str | None = None,
    tags: list[str] | None = None,
    template_diff=None,
    probe_diff=None,
    probe_total: int = 0,
    now: datetime.datetime | None = None,
) -> dict:
    """Build a CycloneDX 1.6 BOM (dict). ``audit_result`` is the output of ``audit_repo``."""
    repo_id = audit_result["repo_id"]
    comp = _repo_component(repo_id, revision)
    if license_id:
        comp["licenses"] = [{"license": {"id": license_id}} if " " not in license_id else {"license": {"name": license_id}}]

    files = sorted(set(audit_result.get("checksums", {})))
    comp["components"] = [
        {"type": "file", "bom-ref": f"{comp['bom-ref']}#{name}", "name": name,
         "hashes": [{"alg": "SHA-256", "content": audit_result["checksums"][name]}]}
        for name in files
    ]

    all_files = files + audit_result.get("risky_pickle_files", []) + audit_result.get("custom_code_files", [])
    props = [
        _prop("total-files", audit_result.get("total_files", 0)),
        _prop("risky-pickle-files", len(audit_result.get("risky_pickle_files", []))),
        _prop("custom-code-files", len(audit_result.get("custom_code_files", []))),
    ]
    for f in audit_result.get("risky_pickle_files", []):
        props.append(_prop("risky-pickle-file", f))
    for f in audit_result.get("custom_code_files", []):
        props.append(_prop("custom-code-file", f))
    formats = detect_formats(all_files, tags)
    if formats:
        props.append(_prop("formats", ",".join(formats)))

    if base_repo_id:
        ancestor = _repo_component(base_repo_id, base_revision)
        comp["pedigree"] = {
            "ancestors": [ancestor],
            "notes": f"Converted/derived from {base_repo_id}. Lineage is declared by the publisher; see properties for checks.",
        }
        props.append(_prop("derived-from", base_repo_id))
        if template_diff is not None:
            props.append(_prop("chat-template-changed", str(bool(template_diff.changed)).lower()))
        if probe_diff is not None:
            regressions = [i for i in probe_diff.items if i.base_safe and not i.derived_safe]
            props += [
                _prop("probe-total", probe_total),
                _prop("probe-regressions", len(regressions)),
                _prop("probe-regression-ids", ",".join(i.id for i in regressions)),
            ]
    comp["properties"] = props

    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": [{"type": "application", "name": "model-audit-lite", "version": __version__}]},
            "component": {k: comp[k] for k in ("type", "bom-ref", "name") + (("version",) if "version" in comp else ())},
        },
        "components": [comp],
    }


def merge_into(existing: dict, ours: dict) -> dict:
    """Add our lineage/audit data to a BOM produced by another generator (matched by component name).

    The existing component keeps all its fields; we append our nested file components, properties and
    ``pedigree`` (only if it has none). If no component matches, ours is appended as a new component.
    """
    out = json.loads(json.dumps(existing))
    new = ours["components"][0]
    target = next((c for c in out.setdefault("components", []) if c.get("name") == new["name"]), None)
    if target is None:
        out["components"].append(new)
        return out
    target.setdefault("components", []).extend(
        c for c in new["components"] if c["name"] not in {x.get("name") for x in target["components"]}
    )
    known = {(p["name"], p["value"]) for p in target.get("properties", [])}
    target.setdefault("properties", []).extend(p for p in new["properties"] if (p["name"], p["value"]) not in known)
    if "pedigree" in new and "pedigree" not in target:
        target["pedigree"] = new["pedigree"]
    tools = out.setdefault("metadata", {}).setdefault("tools", {})
    if isinstance(tools, dict):
        tools.setdefault("components", []).extend(ours["metadata"]["tools"]["components"])
    return out
