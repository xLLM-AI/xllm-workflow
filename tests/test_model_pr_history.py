import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "model-pr-optimization-history" / "scripts" / "query.py"


def run_query(*args):
    return subprocess.run(
        [sys.executable, str(QUERY), *args],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def test_query_supports_model_and_keyword_filters():
    out = run_query("--model", "Qwen3.5", "--keyword", "MTP")
    assert "xllm/qwen35-mtp" in out
    assert "Acceptance Rate" in out or "MTP" in out


def test_query_supports_path_filter():
    out = run_query("--framework", "xllm", "--path", "MTPWorkerImpl::run_validate")
    assert "qwen35-mtp.md" in out
    assert "MTPWorkerImpl::run_validate" in out
