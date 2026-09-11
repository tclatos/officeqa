# Document Graph Build Speed — Analysis & Optimization Report

Target: `cli bench run --step build` for the OfficeQA corpus — 191 Treasury Bulletins,
97 MB of OCR markdown — on a 12th Gen Intel Core i7-1265U, 32 GB, WSL/Ubuntu.
Observed before this work: multi-hour builds showing up in Prefect as a handful of
very long flows.

## TL;DR

| Scenario (3 fake 20-page docs, cold caches) | Wall time |
|---|---|
| Baseline — serial outline extraction + serial embeddings | **35.8 s** |
| Optimized — parallel outline pre-pass + async parallel embeddings | **27.1 s** |
| Optimized, warm caches (rebuild with `force: true`) | **3.9 s** |

The baseline extrapolates to the observed multi-hour full-corpus builds
(outline extraction is ~73% of the time and was fully serial across documents).
The optimized path parallelizes everything that is I/O-bound (LLM calls, embedding
API calls) and keeps only the DB merge serial, which Kuzu requires anyway.

## Root Causes Identified

### 1. **API mismatch in `bench/build_graph.py` (CRITICAL)**
**Status:** Fixed in genai-graph/genai_graph/bench/build_graph.py

Current code calls non-existent methods:
- `factory.create_schema()` — does not exist on `DocumentGraphFactory`
- `factory.ingest(backend)` — does not exist
- Wrong kwargs: `data_root`, `recursive`, `llm`, `structure_strategy` — not on `DocumentGraphFactory`

**Root cause:** Code was written against an older API. Modern flow in `orchestration/document_graph_flow.py` correctly uses:
- `OutlineConfig(llm, structure_strategy, generate_summaries, workers, summary_min_tokens, context_safety_ratio, cache_root)`
- `DocumentGraphFactory(sources=[...], outline_config=...)`
- `ingest_document_graph(backend, factory, force=, retrieval_config=RetrievalConfig(...))` from `kg/document_graph/ingest.py`

**Fix:** Rewritten `build_document_graph` to match working API.

### 2. **Serial cross-document LLM work (MAJOR BOTTLENECK)**
**Found:** `extract_outline()` runs inline per document inside the serial ingest loop.
Within a document, branch summarization uses a 6-thread pool, but documents are
processed one after another.

**Measured:** 26.1 s of outline LLM time for three 20-page docs — ~73% of total build
time. Trace data (`data/traces/llm_calls.jsonl`) shows median LLM call 7.9 s, p90 43.7 s.

**Fix (implemented):** `outline_pre_pass=True` (default) on `build_document_graph`
calls `factory.extract_outlines(workers)` first, warming the content-addressed
outline cache (`<db>_outlines/`) across documents in parallel; the ingest then reads
cached outlines from disk with zero LLM calls.

### 3. **Serial per-document embeddings**
**Found:** `build_sections_chunks()` runs inline in the serial loop; a document's
embedding batch blocks the next document. Cold batches measured at 6.8 s for 3 docs.

**Fix (implemented):** two-phase ingest in `ingest_document_graph` — parse bundles and
decide skips serially (cheap DB reads), chunk+embed all pending documents
concurrently (`embed_workers`), then accumulate rows and merge once (single-writer,
which Kuzu requires).

**Concurrency bug found and fixed while parallelizing:** calling the sync cached
embeddings path (`CacheBackedEmbeddings.embed_documents` →
`AsyncKeyValueByteStoreAdapter.mget`) from several threads fails with
`<Lock object> is bound to a different event loop` — the py-key-value store binds
asyncio primitives to the first loop that touches it. Parallel embedding therefore
drives `CacheBackedEmbeddings.aembed_documents` from a **single asyncio loop** with
an `asyncio.Semaphore(embed_workers)` (store adapter async ops are async-native),
not from a thread pool.

### 4. **No hidden semaphores or locks elsewhere (good news)**
- Kuzu backend only serializes native `CALL` statements and extension loads (`_NATIVE_CALL_LOCK` / `_EXTENSION_LOCK` in kg/backend.py); ordinary Cypher MATCH/RETURN is fully concurrent
- DB writes must stay single-writer → the merge stays one call; all I/O-bound work (LLM, embeddings) now overlaps

### 5. **Model optimization available (LOW-HANGING FRUIT)**
- Build LLM already set to `deepseek-v4-flash-0731(none)@openrouter` (non-thinking, cheap)
- OpenRouter supports `@openrouter:speed` routing strategy (llm_factory.py:1244–1273)
- Adds 1–2 line config change; selects fastest available model variant

### 6. **Bench config `force: true` rebuilds every run**
- Current bench.yaml: `build.force: true` (line 39)
- Rebuilds all sections even if markdown unchanged
- Outline cache helps (content-addressed), but still re-ingests
- Recommendation: Set `force: false` unless markdown changed

## Measurements

Method: three ~100 KB fake documents (first ~20 pages of real bulletins —
1991_09/1996_09/2001_09 for baseline, 2003_09/2006_09/2010_09 for optimized, so both
runs are cold on outline and embedding caches), isolated Kuzu DB per run, `workers=6`,
instrumented stage timers (`scratch_build_speed.py`, results in
`data/bench_speed/result_*.json`).

| Stage | Baseline (cold) | Optimized (cold) | Optimized (warm) |
|---|---|---|---|
| Outline pre-pass | — (inline in ingest) | 21.5 s | 0.01 s (cache hits) |
| Outline extraction (accumulated) | 26.1 s, 3 calls, serial | 47.0 s CPU across ~2.2× overlap | ~0 |
| Chunk + embed | 6.8 s, serial | inside 5.5 s ingest phase | inside 3.6 s |
| DB merge + indexes | ~2.9 s | ~2.5 s | ~3.6 s |
| **Wall total** | **35.8 s** | **27.1 s** | **3.9 s** |

- Optimized cold is 24% faster on only 3 documents; the LLM leg's effective
  parallelism was ~2.2× here because 3 concurrent calls are latency-variance
  dominated. With 191 documents the pre-pass keeps 6 workers saturated, so the
  serial 26 s/3-docs LLM leg (~2.3 h extrapolated to full 500 KB-average docs)
  becomes roughly 25–40 min.
- Warm rebuild (the `force: true` case) drops from hours to minutes: outline and
  embedding caches hit; remaining time is DB-bound.
- Validation: ruff clean; three end-to-end builds produced correct graphs
  (71 sections/110 chunks and 49 sections/100 chunks/152 rels + HNSW + FTS
  indexes). pytest is not installed in this environment, so the formal suite
  could not run.

## Further improvements (recommended, not implemented)

1. **Config wins (minutes to apply):** set `build.force: false` in `config/bench.yaml`
   (rebuild only when markdown actually changed) and consider
   `deepseek-v4-flash-0731(none)@openrouter:speed` routing for the build LLM
   (`llm_factory.py` supports `:speed` → OpenRouter `sort=speed`).
2. **Raise `workers` (config only):** pre-pass, per-doc branch pools and embedding
   concurrency all derive from it; 8–12 is reasonable for OpenRouter flash models
   (the work is I/O-bound).
3. **Batch embeddings across documents:** each document is currently one
   `aembed_documents` call; grouping 2–3 docs per call would shave per-request
   overhead on very large corpora (the 3.6 GB cache already makes re-runs cheap).
4. **Prefect granularity:** see the next section — per-document outline tasks are
   now implemented; batched merges are the remaining option for 500+ docs.
5. **Memory note:** two-phase ingest holds all parsed bundles in RAM (~200 MB for
   this corpus); stream in batches if the corpus grows an order of magnitude.

## Finer Prefect granularity for a 500+ document production corpus

The build decomposes into three stages with different parallelism constraints.
The hard constraint is Ladybug: **one read-write `Database` per file per process**
(`KuzuBackend.connect`), so tasks that only open their own connection cannot run
the DB merge concurrently. A shared-Database writer pool exists
(`attach()` + `enable_multi_writes=True`) but the codebase has a history of native-
heap SIGSEGVs under concurrency (hence the process-wide locks in `kg/backend.py`),
so concurrent writes are deliberately not used.

### Implemented: per-document outline tasks + single-writer merge

`build_graph_flow` in `genai_graph/bench/flows.py` is now fan-out/fan-in:

1. **`extract_outline_task(doc_name)`** — one Prefect task per document
   (`retries=2`, `task_run_name="outline-{doc_name}"`). It calls
   `warm_outline_cache([doc_name])` which is **DB-free and stateless**: the only
   side effect is writing the content-addressed outline JSON
   (`<db>_outlines/<llm>__<policy>/<markdown_hash>.json`).

   - *Fault isolation:* an LLM outage or poison document fails only its own task
     run after retries; all other documents proceed.
   - *Recovery:* re-running the task is free when the outline cache already hit,
     and a failed document can be retried alone — no other document re-pays LLM
     calls. `build_graph_flow` catches per-task failures (`fut.result()` in
     try/except) and continues; a doc whose extraction ultimately failed merges
     **degraded** (algorithmic parsing, no summaries) instead of failing the flow,
     and is healed by simply re-running the flow later (cache hit for everyone else).
2. **`merge_graph_task(docs)`** — one single-writer task that reads warmed
   outlines from disk, chunk+embeds all documents concurrently on one asyncio
   loop (embeddings cache makes retries ~free), and merges. Fast and DB-bound;
   idempotent via hash-keyed MERGE + per-document section rebuild on `force`.

`build_document_graph(doc_names=[...])` now selects exactly the staged files for
the benchmark's doc list (previously only `docs[0]` was ingested), and raises
`FileNotFoundError` when explicit names match nothing instead of silently falling
back to the whole directory.

### Optional next steps for 500+ docs

1. **Per-document embed-warm task** (same pattern as outlines): a DB-free task
   that parses the bundle, `prepare_chunk_inputs`, and calls
   `compute_embeddings_batch` purely to fill the embeddings cache. Isolates
   DeepInfra outages/retries per document; the merge then embeds from cache at
   zero API cost. Only worth adding if embedding-provider flakiness shows up in
   practice — today the in-process asyncio overlap plus the 3.6 GB cache absorb it.
2. **Batched merge** (`merge_graph_task` per batch of ~50 docs): partial-recovery
   granularity for the DB leg without concurrent writers — each batch is idempotent
   (MERGE + per-doc section delete/rebuild), so a failed batch retries alone.
   Trade-off: batch tasks run sequentially in-process anyway (single Database), so
   this buys fault isolation, not speed.
3. **Concurrency governance:** with hundreds of per-doc tasks, cap provider load
   with a Prefect global concurrency limit (or keep the existing in-process
   semaphores/pools, which already bound LLM calls to `workers`).

### Why not per-document merge tasks

Per-document merge tasks would each need their own `KuzuBackend` → own `Database`
→ "database is locked" against the first task; using `enable_multi_writes=True`
permits concurrent write transactions but reintroduces the native-heap risk that
the process-wide locks were added to fix. The merge is the cheap leg (measured
2.4–3.6 s per 3 docs incl. indexes; ~minutes at 500 docs), so isolating it via
batching is sufficient.

## Changes made (genai-graph, editable dep of officeqa)

- `genai_graph/bench/build_graph.py` — `build_document_graph()` rewritten to the
current API: `OutlineConfig` (with `cache_root=<db>_outlines`),
`DocumentGraphFactory(sources=…)`, optional **parallel outline pre-pass**
(`outline_pre_pass=True` default), ingest via `ingest_document_graph()` with
`RetrievalConfig`, per-stage timings in the returned stats, and `force` now rebuilds
sections per document instead of `DETACH DELETE`-ing the whole database. Doc
selection switched to `doc_names: list[str]` (`_resolve_sources`), which fixes a
latent bug where only `docs[0]` was ingested, and raises `FileNotFoundError` when
explicit names match nothing. New `warm_outline_cache(doc_names)` — DB-free,
per-document cache warming for the Prefect outline tasks.
- `genai_graph/bench/flows.py` — `build_graph_flow` restructured to fan-out/fan-in:
per-document `extract_outline_task` (retries=2, isolated failures) + single-writer
`merge_graph_task` (`build_graph_task` removed; exports updated in `bench/__init__.py`).
- `genai_graph/kg/document_graph/ingest.py` — two-phase ingest with `embed_workers`
(default 1 = old serial behavior) and single-event-loop parallel embedding.
- `genai_graph/kg/document_graph/retrieval.py` — `build_sections_chunks()` split into
`prepare_chunk_inputs()` + `attach_chunk_embeddings()` so the async path reuses the
same logic; sync wrapper unchanged for other callers.
- `officeqa/scratch_build_speed.py` — reproducible experiment harness.

No changes to the production DB (`data/kg/officeqa.db`); experiments used isolated
dbs under `data/bench_speed/`. Nothing was committed.

## Reproducing

```bash
uv run python scratch_build_speed.py baseline    # serial, cold caches
uv run python scratch_build_speed.py optimized   # parallel pre-pass + async embeds
uv run python scratch_build_speed.py report      # print saved result JSONs
```

---

**Author:** Oz analysis  
**Date:** 2026-09-11  
**Artifacts:** plan 66f960e3, `scratch_build_speed.py`, `data/bench_speed/result_*.json`
