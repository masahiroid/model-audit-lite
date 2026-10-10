"""Builds probe items by applying safeguard-bypass wrapper templates to
benchmark behaviors.

The wrapper templates (the "packaging" — e.g. framing a request as an
authorized exercise, or seeding the assistant turn via `assistant_prefill`)
are NOT shipped with this tool. They are loaded from an external YAML the
operator supplies, so the attack phrasing lives with the operator, not in the
distributed package. This module only substitutes each benchmark behavior into
the `{behavior}` slot and pairs it with the template's optional prefill.

Wrapper YAML schema (a list of):
    id: <stable id>
    category: <technique family, e.g. pretext-exercise | prefill-injection>
    user_template: "... {behavior} ..."   # {behavior} <- benchmark behavior
    assistant_prefill: "..."              # optional; seeds the assistant turn
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..constants import BEHAVIOR_PLACEHOLDER

_PROBE_ID_SEPARATOR = "::"
_REQUIRED_WRAPPER_FIELDS = ("id", "category", "user_template")


def load_wrappers(yaml_path: str | Path) -> list[dict]:
    with open(yaml_path, encoding="utf-8") as f:
        wrappers = yaml.safe_load(f)
    if not isinstance(wrappers, list) or not wrappers:
        raise ValueError(f"{yaml_path} must be a non-empty YAML list of wrapper templates")
    for wrapper in wrappers:
        missing = [field for field in _REQUIRED_WRAPPER_FIELDS if field not in wrapper]
        if missing:
            raise ValueError(f"wrapper {wrapper.get('id', '?')} is missing fields: {', '.join(missing)}")
    return wrappers


def build_probes(behaviors: list[str], wrappers: list[dict]) -> list[dict]:
    """Cross product: every behavior wrapped by every template. Each probe is a
    dict `run_probes` understands ({id, category, prompt, assistant_prefill})."""
    probes = []
    for wrapper in wrappers:
        template = wrapper["user_template"]
        prefill = wrapper.get("assistant_prefill", "")
        for index, behavior in enumerate(behaviors):
            prompt = template.format(**{BEHAVIOR_PLACEHOLDER: behavior})
            probes.append(
                {
                    "id": f"{wrapper['id']}{_PROBE_ID_SEPARATOR}{index}",
                    "category": wrapper["category"],
                    "prompt": prompt,
                    "assistant_prefill": prefill,
                }
            )
    return probes
