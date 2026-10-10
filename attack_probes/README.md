# attack_probes

Safeguard-bypass probing assets for `model-audit-lite`, kept here under version
control so runs are reproducible.

## Contents

- **`wrappers.yaml`** — safeguard-bypass wrapper templates (pretext / roleplay
  framing). Auto-generated from JailbreakBench's JBC *manual* artifacts (MIT);
  each `user_template` is a published jailbreak template with its benchmark goal
  replaced by the `{behavior}` placeholder. Not authored here.
- **`build_wrappers.py`** — regenerates `wrappers.yaml` from the upstream
  artifacts (`python attack_probes/build_wrappers.py`), so the provenance of
  every template is traceable to the source.
- **`fetch_behaviors.sh`** — downloads the benchmark behavior CSVs
  (HarmBench / JailbreakBench, both MIT) into `benchmarks/` on demand. The
  behavior corpora are fetched, not committed (see `.gitignore`).

## Usage

```bash
# 1. get the behaviors (once)
./attack_probes/fetch_behaviors.sh

# 2. measure whether a converted model still refuses when behaviors are wrapped
model-audit-lite probe your/model --backend mlx-lm \
  --behaviors attack_probes/benchmarks/harmbench/harmbench_behaviors_text_all.csv \
  --wrappers  attack_probes/wrappers.yaml --limit 50
```

`wrappers.yaml` is deliberately kept out of the installed PyPI package (it is
not listed in `package-data`): the templates live in the source repo for
reproducibility, not bundled into every `pip install`. A prefill-style wrapper
(`assistant_prefill:`) can be added by hand — the runner supports it — but none
is generated here because JailbreakBench ships no prefill artifact to derive
one from.

## Licensing

Wrapper templates derive from [JailbreakBench artifacts](https://github.com/JailbreakBench/artifacts)
(MIT). Behavior corpora are [HarmBench](https://github.com/centerforaisafety/HarmBench)
(MIT) and [JailbreakBench](https://github.com/JailbreakBench/jailbreakbench) (MIT).
These are published, audit-oriented benchmarks; use them only to evaluate models
you are authorized to test.
