"""Download OfficeQA source files (transformed text or PDF) from Hugging Face.

OfficeQA stores pre-parsed/transformed text files under
``treasury_bulletins_parsed/transformed/<doc_name>.txt`` and original PDFs under
``treasury_bulletin_pdfs/<doc_name>.pdf``.

By default, this fetches the transformed text file directly into ``data/markdown_multi/``
so OCR is completely bypassed while preserving tabular text and structure.

Usage:
```bash
uv run cli bench run --step fetch
uv run cli bench run --step fetch -d treasury_bulletin_1941_01
```
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download
from loguru import logger

from officeqa.bench._env import MARKDOWN_DIR, PDFS_DIR, ensure_dirs, load_env
from officeqa.bench.load_dataset import DATASET_ID, TARGET_PATH


def resolve_doc_name(doc_name: str | None) -> str:
    """Return *doc_name* or read the previously selected target from disk."""
    if doc_name:
        return doc_name
    if TARGET_PATH.exists():
        return TARGET_PATH.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "No --doc given and no target_doc.txt found; run load_dataset first."
    )


def _clean_stem(doc_name: str) -> str:
    """Strip extension from doc_name if present."""
    s = doc_name.strip()
    if s.endswith(".txt") or s.endswith(".pdf") or s.endswith(".md"):
        return Path(s).stem
    return s


def fetch_doc(
    doc_name: str,
    *,
    markdown_dir: Path | None = None,
    force: bool = False,
) -> str:
    """Download the transformed document from Hugging Face into markdown_dir.

    Downloads ``treasury_bulletins_parsed/transformed/<clean_stem>.txt`` from the
    gated ``databricks/officeqa`` repo and saves it as ``<clean_stem>.md`` in
    ``markdown_dir`` (defaulting to ``MARKDOWN_DIR``).
    """
    ensure_dirs()
    load_env()
    base = markdown_dir or MARKDOWN_DIR
    base.mkdir(parents=True, exist_ok=True)

    stem = _clean_stem(doc_name)
    dest_path = base / f"{stem}.md"

    if dest_path.exists() and dest_path.stat().st_size > 0 and not force:
        logger.info(
            "Document already present: {} ({} bytes)", dest_path, dest_path.stat().st_size
        )
        return str(dest_path)

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    hf_rel_path = f"treasury_bulletins_parsed/transformed/{stem}.txt"
    logger.info("Downloading {} from HF repo {}", hf_rel_path, DATASET_ID)

    downloaded = hf_hub_download(
        repo_id=DATASET_ID,
        filename=hf_rel_path,
        repo_type="dataset",
        token=token,
    )

    shutil.copy2(downloaded, dest_path)
    logger.success("Saved transformed doc to {} ({} bytes)", dest_path, dest_path.stat().st_size)
    return str(dest_path)


def fetch_pdf(doc_name: str, *, pdfs_dir: Path | None = None) -> str:
    """Download ``<doc_name>.pdf`` into the pdfs dir and return its path."""
    ensure_dirs()
    load_env()
    base = pdfs_dir or PDFS_DIR
    base.mkdir(parents=True, exist_ok=True)

    stem = _clean_stem(doc_name)
    pdf_path = base / f"{stem}.pdf"
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        logger.info(
            "PDF already present: {} ({} bytes)", pdf_path, pdf_path.stat().st_size
        )
        return str(pdf_path)

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    hf_rel_path = f"treasury_bulletin_pdfs/{stem}.pdf"
    logger.info("Downloading {} from HF repo {}", hf_rel_path, DATASET_ID)

    downloaded = hf_hub_download(
        repo_id=DATASET_ID,
        filename=hf_rel_path,
        repo_type="dataset",
        token=token,
    )

    shutil.copy2(downloaded, pdf_path)
    logger.success("Saved {} ({} bytes)", pdf_path, pdf_path.stat().st_size)
    return str(pdf_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Download an OfficeQA transformed document or PDF.")
    parser.add_argument(
        "--doc", default=None, help="doc_name to download (default: selected target)."
    )
    parser.add_argument(
        "--pdf", action="store_true", help="Download raw PDF instead of transformed markdown text."
    )
    args = parser.parse_args(argv)

    doc_names = resolve_doc_name(args.doc).split(",")
    for d in doc_names:
        if args.pdf:
            path = fetch_pdf(d)
            print(f"pdf={path}")
        else:
            path = fetch_doc(d)
            print(f"doc={path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
