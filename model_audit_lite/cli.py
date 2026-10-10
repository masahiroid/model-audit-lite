"""model-audit-lite CLI

使い方:
    model-audit-lite audit <repo_id>
        配布物としての安全性監査のみ（pickle検出・カスタムコード検出・チェックサム）。
        モデルのロードは不要で、どんなリポジトリにも使える。

    model-audit-lite probe <repo_id> --backend mlx-lm [--lang ja|en]
        簡易安全性プローブ（既知の攻撃パターンでの生成テスト）。モデルのロードが必要。

    model-audit-lite full <repo_id> --backend mlx-lm [--lang ja|en] [-o SECURITY.md]
        両方を実行し、Markdownレポートを書き出す。

    model-audit-lite scan <repo_id> [--base <source_repo_id>] [--probes] [-o audit-out/]
        上記を1コマンドで実行し、report.md・bom.json・summary.json（CI用、--fail-on）を出力する統合コマンド。

    model-audit-lite bom <repo_id> [--base <source_repo_id>] [--merge existing-bom.json] [-o bom.json]
        CycloneDX 1.6 ML-BOM（ファイルのチェックサム・指摘・変換系譜）。他ツールのBOMにマージ可能。

    model-audit-lite compare <base_repo_id> <derived_repo_id> [--probes] [--lang ja|en] [-o report.md]
        変換の完全性監査。変換元リポジトリと変換後リポジトリの`chat_template`を比較し、
        改変を検出する。`--probes`を付けると、同一の安全性プローブを両方のモデルに実行し、
        判定が変化した項目（特に安全→危険のレグレッション）だけを報告する。
"""
from __future__ import annotations

import argparse
import sys

from .probes.backends import free_model_memory, load_backend
from .constants import DEFAULT_MAX_TOKENS
from .audit.conversion import diff_chat_template, diff_probe_results
from .audit.files import audit_repo
from .probes.behaviors import load_behaviors
from .probes.runner import run_probes
from .probes.wrapping import build_probes, load_wrappers
from .reporting.report import build_file_audit_section, build_probe_section, write_comparison_report, write_security_md


def _resolve_probes(args):
    """Returns (probes, source_label). With --behaviors/--wrappers, probes come
    from the benchmark CSV wrapped by the operator's templates; otherwise the
    built-in prompt set named by --probe-set / --lang is used (probes=None)."""
    behaviors_path = getattr(args, "behaviors", None)
    wrappers_path = getattr(args, "wrappers", None)
    if behaviors_path or wrappers_path:
        if not (behaviors_path and wrappers_path):
            raise SystemExit("--behaviors and --wrappers must be given together")
        behaviors = load_behaviors(behaviors_path, limit=getattr(args, "limit", 0))
        probes = build_probes(behaviors, load_wrappers(wrappers_path))
        return probes, f"wrapped:{len(probes)}"
    return None, getattr(args, "probe_set", None) or args.lang


def _run_probe_set(backend, repo_id, max_tokens, thinking, probes, source):
    fn = load_backend(backend, repo_id, max_tokens, thinking)
    try:
        return run_probes(fn, prompts=probes, source=source)
    finally:
        del fn
        free_model_memory()  # the two models are never resident together


def _add_wrapped_probe_args(sub_parser) -> None:
    sub_parser.add_argument(
        "--behaviors", default=None,
        help="CSV of behaviors from an audit benchmark (HarmBench/JailbreakBench). Requires --wrappers.",
    )
    sub_parser.add_argument(
        "--wrappers", default=None,
        help="YAML of safeguard-bypass wrapper templates (operator-supplied; not shipped). Requires --behaviors.",
    )
    sub_parser.add_argument(
        "--limit", type=int, default=0, help="Use only the first N behaviors (0 = all).",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="model-audit-lite")
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="File-distribution safety audit only (no model loading)")
    p_audit.add_argument("repo_id")
    p_audit.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_audit.add_argument("-o", "--output", default=None, help="Write markdown to this file instead of stdout")

    p_probe = sub.add_parser("probe", help="Run the safety-probe prompt suite (requires loading the model)")
    p_probe.add_argument("repo_id")
    p_probe.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_probe.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_probe.add_argument("--probe-set", default=None, help="Probe set: ja, en, ja-injection, or a YAML path (default: same as --lang)")
    p_probe.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p_probe.add_argument("--thinking", default="default", choices=["default", "on", "off"], help="chat-template enable_thinking for reasoning models")
    _add_wrapped_probe_args(p_probe)
    p_probe.add_argument("-o", "--output", default=None)

    p_full = sub.add_parser("full", help="Run both file audit and safety probes")
    p_full.add_argument("repo_id")
    p_full.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_full.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_full.add_argument("--probe-set", default=None, help="Probe set: ja, en, ja-injection, or a YAML path (default: same as --lang)")
    p_full.add_argument("--max-tokens", type=int, default=300)
    p_full.add_argument("-o", "--output", default="SECURITY.md")

    p_compare = sub.add_parser(
        "compare",
        help="Conversion-integrity audit: diff chat_template and (optionally) safety-probe results between a source and a converted repo",
    )
    p_compare.add_argument("base_repo_id", help="The original (pre-conversion) repo")
    p_compare.add_argument("derived_repo_id", help="The converted repo")
    p_compare.add_argument("--probes", action="store_true", help="Also run and diff the safety-probe suite (loads both models)")
    p_compare.add_argument("--base-backend", default="transformers", choices=["mlx-lm", "transformers"])
    p_compare.add_argument("--derived-backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_compare.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_compare.add_argument("--max-tokens", type=int, default=300)
    p_compare.add_argument("-o", "--output", default=None)

    p_bom = sub.add_parser(
        "bom",
        help="Write a CycloneDX 1.6 ML-BOM: file checksums, findings and (with --base) conversion lineage; optionally merge into another BOM",
    )
    p_bom.add_argument("repo_id")
    p_bom.add_argument("--base", default=None, help="Source repo this one was converted/derived from (adds pedigree + chat-template check)")
    p_bom.add_argument("--merge", default=None, help="Existing CycloneDX JSON (e.g. from OWASP AIBOM Generator / cdxgen) to merge into")
    p_bom.add_argument("-o", "--output", default=None)

    p_scan = sub.add_parser(
        "scan",
        help="One command: file audit + (with --base) conversion compare + (with --probes) safety probes -> report.md, bom.json, summary.json",
    )
    p_scan.add_argument("repo_id")
    p_scan.add_argument("--base", default=None, help="Source repo (adds chat-template compare, BOM pedigree, and probe regression diff)")
    p_scan.add_argument("--probes", action="store_true", help="Also run the safety probes (loads the model; with --base, on both)")
    p_scan.add_argument("--backend", default="mlx-lm", choices=["mlx-lm", "transformers"])
    p_scan.add_argument("--base-backend", default="transformers", choices=["mlx-lm", "transformers"])
    p_scan.add_argument("--probe-set", default=None, help="ja, en, ja-injection or a YAML path (default: --lang)")
    p_scan.add_argument("--lang", default="ja", choices=["ja", "en"])
    p_scan.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p_scan.add_argument("--thinking", default="default", choices=["default", "on", "off"], help="chat-template enable_thinking for reasoning models")
    _add_wrapped_probe_args(p_scan)
    p_scan.add_argument("-o", "--out-dir", default="audit-out")
    p_scan.add_argument("--fail-on", default="fail", choices=["fail", "warn", "never"], help="Exit non-zero on this status (for CI)")

    args = parser.parse_args(argv)

    if args.command == "audit":
        result = audit_repo(args.repo_id)
        md = build_file_audit_section(result, lang=getattr(args, "lang", "ja"))
        _emit(md, args.output)

    elif args.command == "probe":
        probes, source = _resolve_probes(args)
        report = _run_probe_set(args.backend, args.repo_id, args.max_tokens, args.thinking, probes, source)
        md = build_probe_section(report, lang=args.lang)
        _emit(md, args.output)

    elif args.command == "full":
        audit_result = audit_repo(args.repo_id)
        probe_report = _run_probe_set(
            args.backend, args.repo_id, args.max_tokens, "default", None, args.probe_set or args.lang
        )
        md = write_security_md(audit_result=audit_result, probe_report=probe_report, repo_id=args.repo_id, lang=args.lang)
        _emit(md, args.output)

    elif args.command == "scan":
        from huggingface_hub import HfApi

        from .reporting.scan import run_scan

        api = HfApi()
        info = api.model_info(args.repo_id)
        card = getattr(info, "card_data", None)
        template_diff = diff_chat_template(args.base, args.repo_id) if args.base else None
        probe_report = probe_diff = None
        probe_total = 0
        if args.probes:
            probes, source = _resolve_probes(args)
            probe_report = _run_probe_set(args.backend, args.repo_id, args.max_tokens, args.thinking, probes, source)
            if args.base:
                base_report = _run_probe_set(
                    args.base_backend, args.base, args.max_tokens, args.thinking, probes, source
                )
                probe_diff = diff_probe_results(base_report, probe_report)
                probe_total = probe_report.total
        summary = run_scan(
            audit_repo(args.repo_id, api=api), args.out_dir, lang=args.lang, base_repo_id=args.base,
            template_diff=template_diff, probe_report=probe_report, probe_diff=probe_diff, probe_total=probe_total,
            revision=info.sha, base_revision=api.model_info(args.base).sha if args.base else None,
            license_id=getattr(card, "license", None) if card else None, tags=list(info.tags or []),
        )
        print(f"[{summary['status'].upper()}] {args.repo_id} -> {args.out_dir}/ (report.md, bom.json, summary.json)", file=sys.stderr)
        if summary["fail"]:
            print("fail: " + ", ".join(summary["fail"]), file=sys.stderr)
        if summary["warn"]:
            print("warn: " + ", ".join(summary["warn"]), file=sys.stderr)
        if args.fail_on == "fail" and summary["status"] == "fail" or args.fail_on == "warn" and summary["status"] != "pass":
            sys.exit(1)

    elif args.command == "bom":
        import json

        from huggingface_hub import HfApi

        from .audit.bom import build_bom, merge_into

        api = HfApi()
        info = api.model_info(args.repo_id)
        card = getattr(info, "card_data", None)
        base_rev = api.model_info(args.base).sha if args.base else None
        bom = build_bom(
            audit_repo(args.repo_id, api=api),
            base_repo_id=args.base,
            base_revision=base_rev,
            revision=info.sha,
            license_id=getattr(card, "license", None) if card else None,
            tags=list(info.tags or []),
            template_diff=diff_chat_template(args.base, args.repo_id) if args.base else None,
        )
        if args.merge:
            with open(args.merge, encoding="utf-8") as f:
                bom = merge_into(json.load(f), bom)
        _emit(json.dumps(bom, ensure_ascii=False, indent=2), args.output)

    elif args.command == "compare":
        template_diff = diff_chat_template(args.base_repo_id, args.derived_repo_id)
        probe_diff = None
        probe_total = 0
        if args.probes:
            base_report = _run_probe_set(args.base_backend, args.base_repo_id, args.max_tokens, "default", None, args.lang)
            derived_report = _run_probe_set(args.derived_backend, args.derived_repo_id, args.max_tokens, "default", None, args.lang)
            probe_diff = diff_probe_results(base_report, derived_report)
            probe_total = derived_report.total
        md = write_comparison_report(
            template_diff=template_diff,
            probe_diff=probe_diff,
            probe_total=probe_total,
            base_repo_id=args.base_repo_id,
            derived_repo_id=args.derived_repo_id,
            lang=args.lang,
        )
        _emit(md, args.output)


def _emit(text: str, output: str | None):
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Written to {output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
