#!/bin/bash
# Download the benchmark behavior CSVs used with wrappers.yaml. These are the
# harmful (and benign) request corpora; they are fetched on demand rather than
# committed. Both are MIT-licensed.
set -euo pipefail
DEST="${1:-./benchmarks}"
mkdir -p "$DEST/harmbench" "$DEST/jailbreakbench"
curl -fL -o "$DEST/harmbench/harmbench_behaviors_text_all.csv" \
  https://raw.githubusercontent.com/centerforaisafety/HarmBench/main/data/behavior_datasets/harmbench_behaviors_text_all.csv
curl -fL -o "$DEST/jailbreakbench/harmful-behaviors.csv" \
  https://raw.githubusercontent.com/JailbreakBench/jailbreakbench/main/src/jailbreakbench/data/behaviors.csv || \
  python3 -c "from huggingface_hub import hf_hub_download as d; d('JailbreakBench/JBB-Behaviors','data/harmful-behaviors.csv',repo_type='dataset',local_dir='$DEST/jailbreakbench')"
echo "behaviors -> $DEST"
