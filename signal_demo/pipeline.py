from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from .contracts import ROOT, load_contract, strict_json
from .detection import build_review_queue, fit_reference, monitor
from .evaluation import evaluate
from .quality import inspect
from .receipts import verify_semantics
from .synthetic import generate
from .warehouse import build

DATA_ARTIFACTS = (
    "synthetic_signal_records.csv",
    "synthetic_injection_truth.csv",
    "quality_buckets.csv",
    "signal_monitor.csv",
    "review_queue.csv",
    "reference.json",
    "evaluation.json",
    "signal_quality.json",
    "signal_monitor.duckdb",
)
RECEIPT_ARTIFACTS = (*DATA_ARTIFACTS, "manifest.json")
QUEUE_FIELDS = [
    "queue_rank",
    "alert_id",
    "area_id",
    "event_day",
    "alert_type",
    "priority",
    "standardized_residual",
    "reference_id",
    "policy_id",
    "reason_codes",
    "review_status",
    "recommended_action",
    "adverse_action_authorized",
]
BOUNDARY = "engineering pipeline validation; no scientific or production claim"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def verify_receipt(output: Path) -> dict:
    output = Path(output)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("real signal artifact directory required")
    if any(p.is_symlink() or not p.is_file() for p in output.iterdir()):
        raise ValueError("regular signal artifact files required")
    receipt = strict_json((output / "run_receipt.json").read_text())
    if not isinstance(receipt, dict):
        raise ValueError("signal receipt object required")
    if receipt.get("status") != "PASS" or set(receipt.get("artifacts", {})) != set(
        RECEIPT_ARTIFACTS
    ):
        raise ValueError("incomplete signal run receipt")
    if (
        set(receipt)
        != {
            "status",
            "owner",
            "reference_id",
            "artifacts",
            "checks",
            "boundary",
            "unsigned",
            "authenticity_established",
        }
        or receipt["owner"] != "complaint_signal_demo_v1"
        or receipt["unsigned"] is not True
        or receipt["authenticity_established"] is not False
        or receipt["boundary"] != BOUNDARY
        or not isinstance(receipt["checks"], dict)
        or set(receipt["checks"]) != {"python_sql_parity", "reference_replay_equal"}
        or any(v is not True for v in receipt["checks"].values())
    ):
        raise ValueError("invalid unsigned signal receipt contract")
    names = {p.name for p in output.iterdir()}
    if names not in (
        set(RECEIPT_ARTIFACTS) | {"run_receipt.json"},
        set(RECEIPT_ARTIFACTS) | {"run_receipt.json", ".signal_demo.lock"},
    ):
        raise ValueError("unexpected signal artifact inventory")
    for name in RECEIPT_ARTIFACTS:
        path = output / name
        if (
            path.is_symlink()
            or not path.is_file()
            or digest(path) != receipt["artifacts"][name]
        ):
            raise ValueError(f"signal artifact integrity failure: {name}")
    manifest = strict_json((output / "manifest.json").read_text())
    if (
        manifest["reference_id"] != receipt["reference_id"]
        or manifest["synthetic_only"] is not True
    ):
        raise ValueError("signal manifest/reference mismatch")
    verify_semantics(output, receipt)
    return receipt


def make_manifest(c, reference):
    sources = sorted(
        [
            *ROOT.glob("signal_demo/*.py"),
            ROOT / "contracts/signal_contract.json",
            ROOT / "sql/signals.sql",
            ROOT / "requirements.txt",
            ROOT / "run_signal_demo.sh",
        ]
    )
    return {
        "synthetic_only": True,
        "scientific_results_claimed": False,
        "policy": c,
        "reference_id": reference["reference_id"],
        "baseline_input_sha256": reference["baseline_input_sha256"],
        "dependencies": {name: version(name) for name in ("numpy", "duckdb", "pytest")},
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
        "determinism": "CSV/JSON data and scores; DuckDB file bytes can vary between equivalent builds",
    }


def quality_report(qa, quality, rows):
    reasons = Counter(code for q in quality for code in json.loads(q["reason_codes"]))
    return {
        **qa,
        "scheduled_buckets": len(quality),
        "raw_records": len(rows),
        "admitted_buckets": sum(q["admitted"] for q in quality),
        "blocked_buckets": sum(not q["admitted"] for q in quality),
        "valid_zero_buckets": sum(q["valid_zero"] for q in quality),
        "reason_counts": dict(sorted(reasons.items())),
        "reference_replay_equal": True,
    }


def _stage(output: Path, c: dict) -> dict:
    rows, truth = generate(c)
    quality = inspect(rows, c)
    reference = fit_reference(rows, quality, c)
    scored = monitor(quality, reference, c)
    queue = build_review_queue(scored)
    write_json(output / "reference.json", reference)
    replay = monitor(quality, strict_json((output / "reference.json").read_text()), c)
    if replay != scored or build_review_queue(replay) != queue:
        raise ValueError("persisted reference replay mismatch")
    qa = build(
        output / "signal_monitor.duckdb", rows, quality, reference, scored, queue
    )
    report = quality_report(qa, quality, rows)
    for name, records in [
        ("synthetic_signal_records.csv", rows),
        ("synthetic_injection_truth.csv", truth),
        ("quality_buckets.csv", quality),
        ("signal_monitor.csv", scored),
    ]:
        write_csv(output / name, records)
    write_csv(output / "review_queue.csv", queue, QUEUE_FIELDS)
    write_json(output / "signal_quality.json", report)
    write_json(output / "evaluation.json", evaluate(scored, truth, reference, c))
    manifest = make_manifest(c, reference)
    write_json(output / "manifest.json", manifest)
    receipt = {
        "status": "PASS",
        "reference_id": reference["reference_id"],
        "artifacts": {name: digest(output / name) for name in RECEIPT_ARTIFACTS},
        "checks": {"python_sql_parity": True, "reference_replay_equal": True},
        "boundary": BOUNDARY,
        "owner": "complaint_signal_demo_v1",
        "unsigned": True,
        "authenticity_established": False,
    }
    write_json(output / "run_receipt.json", receipt)
    verify_receipt(output)
    return receipt


def run(output: Path = ROOT / "outputs/signals") -> dict:
    output = Path(output).absolute()
    if output.is_symlink():
        raise ValueError("symlink signal output prohibited")
    output.parent.mkdir(parents=True, exist_ok=True)
    output = output.parent.resolve() / output.name
    if lock_path(output).is_symlink():
        raise ValueError("symlink signal lock prohibited")
    with lock_path(output).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise RuntimeError(
                "signal demo already running for this output directory"
            ) from e
        try:
            if output.exists():
                if not output.is_dir():
                    raise ValueError("signal output must be a directory")
                names = {p.name for p in output.iterdir()}
                if names and names not in (
                    set(RECEIPT_ARTIFACTS) | {"run_receipt.json"},
                    set(RECEIPT_ARTIFACTS) | {"run_receipt.json", ".signal_demo.lock"},
                ):
                    raise ValueError("refusing to overwrite unrecognized signal output")
                if any(p.is_symlink() or not p.is_file() for p in output.iterdir()):
                    raise ValueError("unsafe existing signal artifact")
            with tempfile.TemporaryDirectory(
                prefix=".stage-", dir=output.parent
            ) as tmp:
                stage = Path(tmp)
                receipt = _stage(stage, load_contract())
                backup = None
                if output.exists():
                    backup = Path(
                        tempfile.mkdtemp(prefix=".backup-", dir=output.parent)
                    )
                    backup.rmdir()
                    output.rename(backup)
                try:
                    stage.rename(output)
                except BaseException:
                    if backup is not None:
                        backup.rename(output)
                    raise
                if backup is not None:
                    shutil.rmtree(backup)
            return receipt
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def lock_path(output):
    return output.parent / ("." + output.name + ".signal-demo.lock")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run or verify the fabricated complaint-signal demonstration"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/signals")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    receipt = verify_receipt(args.output) if args.verify_only else run(args.output)
    print(f"SIGNAL_DEMO_STATUS={receipt['status']} reference={receipt['reference_id']}")


if __name__ == "__main__":
    main()
