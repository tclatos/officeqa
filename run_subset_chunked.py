"""Run the frozen benchmark subset in chunks, one process per chunk.

The Ladybug buffer pool still fails after ~14 questions in a single long-lived
process (see report/DECISION_NAVIGATION_33Q_REPORT.md §3.1): the residual growth
is on the agent side, and once native allocation fails every later graph query
errors out and the run's remaining questions score zero. Until that is fixed,
running the subset as several short-lived processes keeps every question on a
healthy database.

Each chunk runs the questions and then grades them, so a failure mid-way still
leaves earlier chunks fully scored.

Usage:
```
uv run --no-sync python run_subset_chunked.py -p decision_fast -n 8
```
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

SUBSET = Path("bench/officeqa_dm_subset.json")


def _run(cmd: list[str], env: dict[str, str]) -> int:
    """Run one command, streaming its output; return the exit code."""
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, env=env, check=False).returncode


def main() -> int:
    """Split the subset into chunks and run + grade each in its own process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-p", "--profile", default="decision_fast", help="Bench profile name")
    parser.add_argument("-n", "--chunk-size", type=int, default=8, help="Questions per process")
    parser.add_argument("--subset", default=str(SUBSET), help="Frozen subset JSON path")
    parser.add_argument(
        "--keep-monitoring",
        action="store_true",
        help="Leave cloud tracing enabled (default: disabled for a clean memory profile)",
    )
    args = parser.parse_args()

    ids: list[str] = json.loads(Path(args.subset).read_text(encoding="utf-8"))["question_ids"]
    chunks = [ids[i : i + args.chunk_size] for i in range(0, len(ids), args.chunk_size)]

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    if not args.keep_monitoring:
        env.setdefault("GENAI_TK_DISABLE_MONITORING", "1")

    # Grading reuses any score it finds, so a re-run would silently report the
    # PREVIOUS configuration's verdicts. Clear them (with a backup) first.
    scores_path = Path(f"data/officeqa/{args.profile}/scores.jsonl")
    if scores_path.exists() and scores_path.stat().st_size:
        backup = scores_path.with_suffix(".jsonl.bak")
        backup.write_bytes(scores_path.read_bytes())
        scores_path.write_text("", encoding="utf-8")
        print(f"Cleared {scores_path} (previous run backed up to {backup}) — will re-grade", flush=True)

    print(f"Running {len(ids)} question(s) in {len(chunks)} chunk(s) of {args.chunk_size}", flush=True)
    failed_chunks: list[int] = []
    for number, chunk in enumerate(chunks, start=1):
        print(f"\n=== chunk {number}/{len(chunks)} — {len(chunk)} question(s)", flush=True)
        code = _run(
            [
                "uv",
                "run",
                "--no-sync",
                "cli",
                "bench",
                "run",
                "-p",
                args.profile,
                "--rerun",
                "--skip",
                "fetch",
                "--skip",
                "build",
                "-q",
                ",".join(chunk),
            ],
            env,
        )
        if code != 0:
            failed_chunks.append(number)
        # Grade ONLY this chunk: grading reads the latest record per question, so an
        # unfiltered grade would also score questions whose newest record still comes
        # from a previous configuration.
        _run(
            [
                "uv",
                "run",
                "--no-sync",
                "cli",
                "bench",
                "grade",
                "-p",
                args.profile,
                "-q",
                ",".join(chunk),
            ],
            env,
        )

    if failed_chunks:
        print(f"\nChunks that reported a non-zero exit: {failed_chunks}", flush=True)
        return 1
    print("\nAll chunks completed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
