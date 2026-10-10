"""変換の完全性監査: 変換元リポジトリと変換後リポジトリを比較し、変換の過程で
何かが変わっていないか（chat templateの改変、安全性アライメントの劣化など）を検出する。

ファイル配布の安全性（file_audit.py）やモデル単体の安全性プローブ（probes/runner.py）
だけでは見つからない、「変換固有」のリスクを対象にする。具体的には:

- GGUF/MLX/CoreMLなどの変換後リポジトリが同梱する`tokenizer_config.json`の`chat_template`
  が、変換元から変わっていないか（量子化ツールやエクスポートスクリプトがテンプレートを
  書き換える/壊す、あるいは意図的に改ざんされるケースがある。chat templateは推論のたびに
  実行される小さなJinja2プログラムであり、モデルカードや自動スキャンの対象外になりがち）。
- 変換元モデルと変換後モデルに同じ安全性プローブを当てたとき、結果が悪化していないか
  （量子化やフォーマット変換が安全性アライメントを劣化させることがある）。
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError

from ..probes.runner import ProbeReport


def _gguf_template(repo_id: str, repo_type: str = "model") -> str | None:
    """GGUF repos keep the template in the weights file's metadata; read it from there (range requests, no full download)."""
    if repo_type != "model":
        return None
    try:
        from .gguf_template import read_chat_template_from_hub
        ggufs = sorted(f for f in HfApi().list_repo_files(repo_id) if f.endswith(".gguf"))
        return read_chat_template_from_hub(repo_id, ggufs[0]) if ggufs else None
    except Exception:
        return None


def _fetch_chat_template(repo_id: str, repo_type: str = "model") -> str | None:
    """chat templateを取り出す。優先順位:

    1. `chat_template.jinja`（現在のtransformers/Hub標準。単体ファイル）
    2. `tokenizer_config.json`の`chat_template`フィールド（旧来の埋め込み形式。
       list[dict]形式（複数テンプレート）の場合は"default"、無ければ先頭を使う）

    どちらも無ければNoneを返す。
    """
    try:
        path = hf_hub_download(repo_id, "chat_template.jinja", repo_type=repo_type)
        with open(path, encoding="utf-8") as f:
            return f.read()
    except EntryNotFoundError:
        pass

    try:
        path = hf_hub_download(repo_id, "tokenizer_config.json", repo_type=repo_type)
    except EntryNotFoundError:
        return _gguf_template(repo_id, repo_type)
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    template = config.get("chat_template")
    if template is None:
        return _gguf_template(repo_id, repo_type)
    if isinstance(template, list):
        for entry in template:
            if entry.get("name") == "default":
                return entry.get("template")
        return template[0].get("template") if template else None
    return template


@dataclass
class ChatTemplateDiff:
    base_repo_id: str
    derived_repo_id: str
    base_template: str | None
    derived_template: str | None
    changed: bool
    diff_lines: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.base_template is None and self.derived_template is None:
            return "no_template"
        if self.base_template is None and self.derived_template is not None:
            return "added"
        if self.base_template is not None and self.derived_template is None:
            return "removed"
        return "changed" if self.changed else "identical"


def diff_chat_template(base_repo_id: str, derived_repo_id: str, repo_type: str = "model") -> ChatTemplateDiff:
    base = _fetch_chat_template(base_repo_id, repo_type=repo_type)
    derived = _fetch_chat_template(derived_repo_id, repo_type=repo_type)

    changed = (base or "") != (derived or "")
    diff_lines: list[str] = []
    if changed and base is not None and derived is not None:
        diff_lines = list(
            difflib.unified_diff(
                base.splitlines(keepends=True),
                derived.splitlines(keepends=True),
                fromfile=f"{base_repo_id}/tokenizer_config.json#chat_template",
                tofile=f"{derived_repo_id}/tokenizer_config.json#chat_template",
            )
        )

    return ChatTemplateDiff(
        base_repo_id=base_repo_id,
        derived_repo_id=derived_repo_id,
        base_template=base,
        derived_template=derived,
        changed=changed,
        diff_lines=diff_lines,
    )


@dataclass
class ProbeRegression:
    id: str
    category: str
    base_safe: bool
    derived_safe: bool
    base_response: str
    derived_response: str

    @property
    def kind(self) -> str:
        if self.base_safe and not self.derived_safe:
            return "regression"
        if not self.base_safe and self.derived_safe:
            return "improvement"
        return "unchanged"


@dataclass
class ProbeDiff:
    items: list[ProbeRegression] = field(default_factory=list)

    @property
    def regressions(self) -> list[ProbeRegression]:
        return [i for i in self.items if i.kind == "regression"]

    @property
    def improvements(self) -> list[ProbeRegression]:
        return [i for i in self.items if i.kind == "improvement"]


def diff_probe_results(base_report: ProbeReport, derived_report: ProbeReport) -> ProbeDiff:
    """同じプロンプトセットを変換元・変換後それぞれに実行した `ProbeReport` 同士を
    IDで突き合わせ、安全→危険（regression）/ 危険→安全（improvement）の変化を抽出する。
    """
    base_by_id = {r.id: r for r in base_report.results}
    diff = ProbeDiff()
    for derived_r in derived_report.results:
        base_r = base_by_id.get(derived_r.id)
        if base_r is None:
            continue
        diff.items.append(
            ProbeRegression(
                id=derived_r.id,
                category=derived_r.category,
                base_safe=base_r.heuristic_safe,
                derived_safe=derived_r.heuristic_safe,
                base_response=base_r.response,
                derived_response=derived_r.response,
            )
        )
    return diff
