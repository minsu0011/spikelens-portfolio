"""Fail closed on unreviewed files, private providers, secrets and local paths.

Run against this release only. The allowlist reviews paths; Gitleaks independently
scans secrets. This guard is not a guarantee against every possible disclosure.
"""
import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EXTENSIONS = {".pkl", ".pickle", ".joblib", ".onnx", ".pt", ".pth", ".ckpt", ".h5", ".hdf5", ".parquet", ".npy", ".npz", ".ipynb", ".dump", ".sqlite", ".sqlite3", ".pem", ".key"}
PRIVATE_IMPORTS = {"torch", "tensorflow", "sklearn", "xgboost", "lightgbm", "catboost", "joblib", "pickle", "onnxruntime"}
PATTERNS = {
    "windows_user_path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\s\"']+", re.I),
    "private_network_share": re.compile(r"\\\\(?:\d{1,3}\.){3}\d{1,3}\\"),
    "private_network_address": re.compile(r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b"),
    "private_engine_symbol": re.compile("Demo" + "Heuristic|demo-" + "heuristic|app\\.analytics\\.engine"),
    "private_key": re.compile("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "credential_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|AKIA[0-9A-Z]{16})\b"),
    "research_asset_name": re.compile("NAS" + "DAQ_STAGE|STAGE" + "P_ALL|NEGATIVE_" + "GATE|POSITIVE_" + "SPECIALIST|OOF_" + "PREDICTION|Feature_" + "Registry", re.I),
}


def inspect(paths, allowed):
    issues = []
    for relative in paths:
        path = ROOT / relative
        if relative not in allowed:
            issues.append({"path": relative, "rule": "unreviewed_file"})
        if path.suffix.lower() in FORBIDDEN_EXTENSIONS or (path.name.startswith(".env") and path.name != ".env.example"):
            issues.append({"path": relative, "rule": "forbidden_artifact"})
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            issues.append({"path": relative, "rule": "external_dependency_path"})
            continue
        if not path.is_file():
            continue
        body = path.read_bytes()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            continue  # Images also require a separate visual/metadata review.
        text = body.decode("utf-8", errors="replace")
        for rule, pattern in PATTERNS.items():
            if pattern.search(text):
                issues.append({"path": relative, "rule": rule})
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                issues.append({"path": relative, "rule": "python_syntax"})
                continue
            for node in ast.walk(tree):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                if any(module.split(".")[0] in PRIVATE_IMPORTS for module in modules):
                    issues.append({"path": relative, "rule": "private_prediction_dependency"})
            if "app/providers/" in relative:
                if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"fit", "predict", "load_model", "load_state_dict"} for node in ast.walk(tree)):
                    issues.append({"path": relative, "rule": "prediction_provider_call"})
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "public_allowlist.json").read_text(encoding="utf-8"))
    command = ["git", "ls-files", "-z"]
    if args.staged:
        command = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
    paths = [p for p in result.stdout.decode("utf-8").split("\0") if p]
    issues = inspect(paths, set(manifest["files"]))
    output = {"status": "FAIL" if issues else "PASS", "files_scanned": len(paths), "issues": issues, "ORM_table_definitions": "ALLOWED", "secret_scanner": "Run independent Gitleaks scan as well"}
    print(json.dumps(output))
    raise SystemExit(1 if issues else 0)


if __name__ == "__main__":
    main()
