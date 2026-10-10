"""配布物としての安全性監査: pickle形式の検出、カスタムコードの検出、チェックサム計算。

モデルの重み自体の内容（バックドアの有無など）は検証しない。あくまで
「配布形式として安全か」「任意コード実行のリスクがないか」を確認するもの。
"""
import hashlib
import re

from huggingface_hub import HfApi, hf_hub_download

RISKY_EXTENSIONS = {".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt"}
CODE_EXTENSIONS = {".py"}
# Core ML packages store raw tensor blobs as ``<name>.mlpackage/**/weights/weight.bin``. They are not pickle
# (no object deserialization), so they must not be reported as pickle-format weights.
_COREML_BLOB = re.compile(r"\.mlpackage/.*weights/[^/]+\.bin$")


# Files this audit itself publishes or edits: hashing them would be stale the moment they are written.
SELF_REFERENTIAL = {".gitattributes", "README.md", "SECURITY.md", "bom.json"}


def is_risky_pickle(path: str) -> bool:
    if _COREML_BLOB.search(path):
        return False
    return any(path.endswith(ext) for ext in RISKY_EXTENSIONS)


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_repo(repo_id: str, repo_type: str = "model", api: HfApi | None = None) -> dict:
    """指定したHugging Faceリポジトリのファイル一覧を取得し、機械的に安全性チェックを行う。

    Returns:
        dict with keys: repo_id, total_files, risky_pickle_files, custom_code_files, checksums
    """
    api = api or HfApi()
    info = api.model_info(repo_id, files_metadata=True) if repo_type == "model" else api.dataset_info(repo_id, files_metadata=True)
    files = [s.rfilename for s in info.siblings]
    lfs_sha = {s.rfilename: s.lfs.sha256 for s in info.siblings if getattr(s, "lfs", None) and getattr(s.lfs, "sha256", None)}

    risky = [f for f in files if is_risky_pickle(f)]
    code_files = [f for f in files if any(f.endswith(ext) for ext in CODE_EXTENSIONS)]

    # Every file gets a SHA-256. LFS files use the digest the Hub already stores (the LFS oid is the SHA-256 of the
    # content), so large weights are not downloaded; small non-LFS files are downloaded and hashed.
    checksums = {}
    for f in sorted(files):
        if f in SELF_REFERENTIAL:
            continue
        if f in lfs_sha:
            checksums[f] = lfs_sha[f]
        else:
            checksums[f] = _sha256_of(hf_hub_download(repo_id, f, repo_type=repo_type))

    return {
        "repo_id": repo_id,
        "total_files": len(files),
        "risky_pickle_files": risky,
        "custom_code_files": code_files,
        "checksums": checksums,
    }
