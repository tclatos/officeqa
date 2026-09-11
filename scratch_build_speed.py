"""Build-speed experiment for the Document Graph pipeline.

Creates 20-page fake documents from real Treasury Bulletin markdown, then runs
`build_document_graph` twice on cold caches with stage-level instrumentation:

- baseline:  outline extraction inline (serial across docs), embed_workers=1
- optimized: parallel outline pre-pass (workers) + embed_workers=6

Each run uses its own markdown dir + kg_db so outline and embedding caches are
cold, giving an apples-to-apples comparison.

Usage:
    uv run python scratch_build_speed.py baseline
    uv run python scratch_build_speed.py optimized
    uv run python scratch_build_speed.py report   # print saved results
"""

from __future__ import annotations

import json
import shutil
import sys
import threading
import time
from pathlib import Path

RESULTS_DIR = Path("data/bench_speed")
LLM = "deepseek-v4-flash-0731(none)@openrouter"
EMBEDDINGS = "qwen3_06b@deepinfra"
WORKERS = 6

# Distinct source bulletins per mode so caches are cold in both runs.
MODE_SOURCES = {
    "baseline": ["treasury_bulletin_1991_09", "treasury_bulletin_1996_09", "treasury_bulletin_2001_09"],
    "optimized": ["treasury_bulletin_2003_09", "treasury_bulletin_2006_09", "treasury_bulletin_2010_09"],
}
MAX_CHARS = 100_000  # ~20 pages of OCR markdown


def make_fake_docs(mode: str) -> Path:
    """Stage 20-page excerpts of distinct bulletins in an isolated markdown dir."""
    md_dir = RESULTS_DIR / mode / "markdown_multi"
    if md_dir.exists():
        shutil.rmtree(md_dir)
    md_dir.mkdir(parents=True)
    for name in MODE_SOURCES[mode]:
        src = Path(f"data/markdown_multi/{name}.md")
        text = src.read_text(encoding="utf-8", errors="replace")[:MAX_CHARS]
        (md_dir / f"fake_{name}_pdf.md").write_text(text[: text.rfind("\n")], encoding="utf-8")
    return md_dir


class Timer:
    """Thread-safe accumulator for named stage timings and call counts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls: dict[str, list[float]] = {}

    def wrap(self, module, name: str) -> None:
        original = getattr(module, name)

        def timed(*args, **kwargs):
            t0 = time.monotonic()
            try:
                return original(*args, **kwargs)
            finally:
                with self._lock:
                    self.calls.setdefault(name, []).append(time.monotonic() - t0)

        setattr(module, name, timed)

    def summary(self) -> dict[str, dict[str, float]]:
        out = {}
        for name, durs in sorted(self.calls.items()):
            out[name] = {"calls": len(durs), "total_s": round(sum(durs), 2), "max_s": round(max(durs), 2)}
        return out


def install_instrumentation() -> Timer:
    """Patch timed wrappers into the module namespaces used by the build path."""
    import genai_graph.kg.document_graph.ingest as ingest_mod
    import genai_graph.kg.document_graph.outline_extract as outline_mod
    import genai_graph.kg.factories.document_graph_factory as factory_mod
    import genai_graph.kg.ingest.merge as merge_mod

    timer = Timer()
    # Per-document outline extraction (LLM): patch both namespaces — the factory
    # imported it by name, the pre-pass resolves it in outline_extract.
    timer.wrap(outline_mod, "extract_outline")
    timer.wrap(factory_mod, "extract_outline")
    # Per-document chunking + embeddings.
    timer.wrap(ingest_mod, "build_sections_chunks")
    # DB batch merges.
    timer.wrap(merge_mod, "merge_nodes_batch")
    timer.wrap(merge_mod, "merge_relationships_batch")
    return timer


def run(mode: str) -> dict:
    from genai_graph.bench.build_graph import build_document_graph
    from genai_graph.bench.config import load_env

    load_env()
    md_dir = make_fake_docs(mode)
    db = RESULTS_DIR / mode / "kg" / "test.db"
    db.parent.mkdir(parents=True, exist_ok=True)

    timer = install_instrumentation()
    t0 = time.monotonic()
    stats = build_document_graph(
        force=True,
        llm=LLM,
        workers=WORKERS,
        embeddings_id=EMBEDDINGS,
        fts=True,
        markdown_dir=md_dir,
        kg_db=db,
        # knobs under test:
        outline_pre_pass=(mode == "optimized"),
        embed_workers=1 if mode == "baseline" else WORKERS,
    )
    wall = time.monotonic() - t0

    out = {
        "mode": mode,
        "wall_s": round(wall, 2),
        "timings": stats.get("timings", {}),
        "stage_calls": timer.summary(),
        "documents_processed": stats.get("documents_processed"),
        "sections_created": stats.get("sections_created"),
        "chunks_created": stats.get("chunks_created"),
        "warnings": stats.get("warnings", [])[:5],
    }
    (RESULTS_DIR / f"result_{mode}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    return out


def report() -> None:
    for mode in ("baseline", "optimized"):
        p = RESULTS_DIR / f"result_{mode}.json"
        if p.exists():
            print(json.dumps(json.loads(p.read_text()), indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd in ("baseline", "optimized"):
        run(cmd)
    else:
        report()
