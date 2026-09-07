"""Load the OfficeQA dataset and select the target document(s).

Caches the Hugging Face dataset under ``data/officeqa/`` and auto-selects
the single ``doc_name`` with the most questions in the split,
then writes one JSONL row per question for that document.

Usage:
```bash
uv run python -m officeqa.bench.load_dataset
uv run python -m officeqa.bench.load_dataset --doc treasury_bulletin_1941_01
```
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download
from loguru import logger
import pathspec

from officeqa.bench._env import OQA_DIR, ensure_dirs, load_env

DATASET_ID = "databricks/officeqa"
DATASET_CACHE_PRO = OQA_DIR / "officeqa_pro.parquet"
DATASET_CACHE_FULL = OQA_DIR / "officeqa_full.parquet"
QUESTIONS_PATH = OQA_DIR / "questions.jsonl"
TARGET_PATH = OQA_DIR / "target_doc.txt"


def match_docs_by_pathspecs(all_docs: list[str], pathspecs: list[str]) -> list[str]:
    """Filter doc_names using gitwildmatch/gitignore style pathspecs.

    Args:
        all_docs: List of candidate document names.
        pathspecs: List of pathspec patterns (supports ``!`` for exclusion).

    Returns:
        Filtered and stable list of matching document names.
    """
    if not pathspecs:
        return all_docs
    spec = pathspec.PathSpec.from_lines("gitwildmatch", pathspecs)
    matched = [d for d in all_docs if spec.match_file(d)]
    return matched


def _normalize_doc_name(raw_name: str) -> str:
    """Normalize a document filename to its base stem without extension."""
    s = raw_name.strip().replace("\r", "")
    if s.endswith(".txt") or s.endswith(".pdf") or s.endswith(".md"):
        return Path(s).stem
    return s


def _parse_source_files(val: str | None) -> list[str]:
    """Parse source_files string (separated by newlines or commas) into a list of normalized doc stems."""
    if not val or not isinstance(val, str):
        return []
    lines = [
        line.strip() for line in val.replace("\r", "\n").split("\n") if line.strip()
    ]
    return [_normalize_doc_name(line) for line in lines]


def load_officeqa(split: str = "pro") -> pd.DataFrame:
    """Load the OfficeQA dataset as a DataFrame.

    Uses a local parquet cache under ``data/officeqa/`` so repeated runs do not hit Hugging Face.
    """
    ensure_dirs()
    load_env()

    cache_file = DATASET_CACHE_PRO if split == "pro" else DATASET_CACHE_FULL
    if cache_file.exists():
        logger.info("Loading cached dataset from {}", cache_file)
        return pd.read_parquet(cache_file)

    csv_name = "officeqa_pro.csv" if split == "pro" else "officeqa_full.csv"
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    logger.info("Downloading {}/{} from Hugging Face", DATASET_ID, csv_name)

    csv_path = hf_hub_download(
        repo_id=DATASET_ID,
        filename=csv_name,
        repo_type="dataset",
        token=token,
    )
    df = pd.read_csv(csv_path)

    # Enrich df with parsed doc_names and primary doc_name
    df["doc_names"] = df["source_files"].apply(_parse_source_files)
    df["doc_name"] = df["doc_names"].apply(
        lambda names: names[0] if names else "unknown"
    )

    OQA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_file, index=False)
    logger.info("Cached {} rows to {}", len(df), cache_file)
    return df


# Alias for backward compatibility
load_financebench = load_officeqa


def select_target_doc(df: pd.DataFrame) -> str:
    """Return the ``doc_name`` with the most questions in *df*."""
    all_docs: list[str] = []
    for docs in df["doc_names"]:
        all_docs.extend(docs)
    if not all_docs:
        counts = Counter(df["doc_name"].tolist())
        doc_name, n = counts.most_common(1)[0]
    else:
        counts = Counter(all_docs)
        doc_name, n = counts.most_common(1)[0]
    logger.info("Selected target doc: {} ({} questions)", doc_name, n)
    return doc_name


def _clean(value):
    """Return *value* as JSON-safe: pandas/float NaN -> ``None``, numpy ndarray -> list."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def questions_for_doc(df: pd.DataFrame, doc_name: str) -> list[dict]:
    """Return the question rows for *doc_name* as JSON-serialisable dicts."""
    clean_target = _normalize_doc_name(doc_name)
    mask = df["doc_name"].apply(lambda d: _normalize_doc_name(d) == clean_target) | df[
        "doc_names"
    ].apply(lambda docs: any(_normalize_doc_name(d) == clean_target for d in docs))
    sub = df[mask].sort_values("uid")
    rows: list[dict] = []
    for _, row in sub.iterrows():
        raw_doc_names = row.get("doc_names")
        if hasattr(raw_doc_names, "tolist"):
            doc_names_list = raw_doc_names.tolist()
        elif isinstance(raw_doc_names, (list, tuple)):
            doc_names_list = list(raw_doc_names)
        else:
            doc_names_list = [clean_target]

        rows.append(
            {
                "officeqa_id": str(row.get("uid", "")),
                "financebench_id": str(row.get("uid", "")),
                "question": row["question"],
                "answer": str(row["answer"]),
                "source_docs": _clean(row.get("source_docs")),
                "source_files": _clean(row.get("source_files")),
                "doc_name": clean_target,
                "doc_names": doc_names_list,
                "difficulty": _clean(row.get("difficulty")),
            }
        )
    return rows


def questions_for_docs(df: pd.DataFrame, doc_names: list[str]) -> list[dict]:
    """Return the question rows for several *doc_names* as JSON-safe dicts."""
    rows: list[dict] = []
    seen_uids: set[str] = set()
    for name in doc_names:
        for q in questions_for_doc(df, name):
            uid = q["officeqa_id"]
            if uid not in seen_uids:
                seen_uids.add(uid)
                rows.append(q)
    rows.sort(key=lambda r: str(r["officeqa_id"]))
    return rows


def write_questions(df: pd.DataFrame, doc_names: str | list[str]) -> list[dict]:
    """Write the per-question JSONL for *doc_names* (one or several) and record the selection."""
    names = [doc_names] if isinstance(doc_names, str) else list(doc_names)
    clean_names = [_normalize_doc_name(n) for n in names]
    rows = questions_for_docs(df, clean_names)
    with QUESTIONS_PATH.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    TARGET_PATH.write_text(",".join(clean_names), encoding="utf-8")
    logger.info(
        "Wrote {} questions for {} doc(s) to {}",
        len(rows),
        len(clean_names),
        QUESTIONS_PATH,
    )
    return rows


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load OfficeQA and write per-question JSONL for a document."
    )
    parser.add_argument(
        "--doc",
        default=None,
        help="Target doc_name (default: auto-select doc with most questions).",
    )
    parser.add_argument(
        "--split",
        default="pro",
        choices=["pro", "full"],
        help="OfficeQA split to load ('pro' or 'full').",
    )
    args = parser.parse_args(argv)

    df = load_officeqa(split=args.split)
    target = args.doc or select_target_doc(df)
    rows = write_questions(df, target)
    print(f"target_doc={target}")
    print(f"questions_count={len(rows)}")
    print(f"questions_path={QUESTIONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
