from __future__ import annotations

import argparse
from collections import Counter
import csv
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import tempfile

from .contracts import ROOT, load_contract
from .detection import fit_reference, monitor, build_review_queue
from .evaluation import evaluate
from .quality import inspect
from .synthetic import generate
from .warehouse import build

DATA_ARTIFACTS = (
    "synthetic_signal_records.csv", "synthetic_injection_truth.csv", "quality_buckets.csv",
    "signal_monitor.csv", "review_queue.csv", "reference.json", "evaluation.json",
    "signal_quality.json", "signal_monitor.duckdb",
)
RECEIPT_ARTIFACTS = (*DATA_ARTIFACTS, "manifest.json")
QUEUE_FIELDS = [
    "queue_rank", "alert_id", "area_id", "event_day", "alert_type", "priority",
    "standardized_residual", "reference_id", "policy_id", "reason_codes",
    "review_status", "recommended_action", "adverse_action_authorized",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+"\n")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_receipt(output: Path) -> dict:
    receipt = json.loads((output / "run_receipt.json").read_text())
    if receipt.get("status") != "PASS" or set(receipt.get("artifacts", {})) != set(RECEIPT_ARTIFACTS):
        raise ValueError("incomplete signal run receipt")
    for name in RECEIPT_ARTIFACTS:
        path = output / name
        if not path.is_file() or digest(path) != receipt["artifacts"][name]:
            raise ValueError(f"signal artifact integrity failure: {name}")
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest["reference_id"] != receipt["reference_id"] or manifest["synthetic_only"] is not True:
        raise ValueError("signal manifest/reference mismatch")
    return receipt


def _stage(output: Path, c: dict) -> dict:
    rows, truth = generate(c)
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    queue = build_review_queue(scored)
    write_json(output / "reference.json", reference)
    replay = monitor(quality, json.loads((output / "reference.json").read_text()), c)
    if replay != scored or build_review_queue(replay) != queue:
        raise ValueError("persisted reference replay mismatch")
    qa = build(output / "signal_monitor.duckdb", rows, quality, reference, scored, queue)
    reasons = Counter(code for q in quality for code in json.loads(q["reason_codes"]))
    quality_report = {
        **qa, "scheduled_buckets": len(quality), "raw_records": len(rows),
        "admitted_buckets": sum(q["admitted"] for q in quality),
        "blocked_buckets": sum(not q["admitted"] for q in quality),
        "valid_zero_buckets": sum(q["valid_zero"] for q in quality),
        "reason_counts": dict(sorted(reasons.items())), "reference_replay_equal": True,
    }
    for name, records in [
        ("synthetic_signal_records.csv", rows), ("synthetic_injection_truth.csv", truth),
        ("quality_buckets.csv", quality), ("signal_monitor.csv", scored),
    ]:
        write_csv(output / name, records)
    write_csv(output / "review_queue.csv", queue, QUEUE_FIELDS)
    write_json(output / "signal_quality.json", quality_report)
    write_json(output / "evaluation.json", evaluate(scored, truth, reference, c))
    sources = sorted([
        *ROOT.glob("signal_demo/*.py"), ROOT / "contracts/signal_contract.json",
        ROOT / "sql/signals.sql", ROOT / "requirements.txt", ROOT / "run_signal_demo.sh",
    ])
    manifest = {
        "synthetic_only": True, "scientific_results_claimed": False,
        "policy": c, "reference_id": reference["reference_id"],
        "baseline_input_sha256": reference["baseline_input_sha256"],
        "dependencies": {name: version(name) for name in ["numpy", "duckdb", "pytest"]},
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
        "determinism": "CSV/JSON data and scores; DuckDB file bytes can vary between equivalent builds",
    }
    write_json(output / "manifest.json", manifest)
    receipt = {
        "status": "PASS", "reference_id": reference["reference_id"],
        "artifacts": {name: digest(output / name) for name in RECEIPT_ARTIFACTS},
        "checks": {"python_sql_parity": True, "reference_replay_equal": True},
        "boundary": "engineering pipeline validation; no scientific or production claim",
    }
    write_json(output / "run_receipt.json", receipt)
    verify_receipt(output)
    return receipt


def run(output: Path = ROOT / "outputs/signals") -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".signal_demo.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError("signal demo already running for this output directory") from e
        try:
            with tempfile.TemporaryDirectory(prefix=".stage-", dir=output) as tmp:
                stage = Path(tmp)
                receipt = _stage(stage, load_contract())
                # The success receipt is published last. Interrupted publication is
                # detectable by its complete artifact inventory and hashes.
                for name in (*RECEIPT_ARTIFACTS, "run_receipt.json"):
                    os.replace(stage / name, output / name)
            verify_receipt(output)
            return receipt
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or verify the fabricated complaint-signal demonstration")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/signals")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    receipt = verify_receipt(args.output) if args.verify_only else run(args.output)
    print(f"SIGNAL_DEMO_STATUS={receipt['status']} reference={receipt['reference_id']}")


if __name__ == "__main__":
    main()
