# OfficeQA Full Benchmark — Suspension & Resume Notes (2026-09-08 ~08:45)

## State at suspension (2026-09-08 ~17:00 UTC)
- Graph DB (`data/kg/officeqa.db`) is **fully built and verified**: 191 docs, 25,288 sections,
  58,870 chunks, 5,253 summarized, 84,158 relationships, 0 degraded. FTS index `section_fts`
  built, HNSW/vector index present, DB checkpointed cleanly.
- Run phase (step `run`) with **hybrid retrieval (HNSW/BM25 + vector)** has completed all **133 questions**.
  - Final `runs.jsonl`: **133 rows** (all 133 questions ran at least once; 114 error-free).
  - Errors: 17× Recursion limit (chart-heavy questions hitting step limit), 2× network glitches.
  - **CRITICAL PATCH APPLIED**: deepagents middleware bug fixed (67 "Unreachable code" errors were caused
    by raw tool outputs not being wrapped into ToolMessage; patch wraps them automatically).
    The patch lives in `/home/tcl/prj/officeqa/.venv/lib/python3.12/site-packages/deepagents/middleware/filesystem.py`
    — it will persist across agent restarts in this venv.
  - No native crashes (ladybug SIGSEGV); all data safely on disk.

## Next step 1 (optional): retry the 19 error rows
```bash
cd /home/tcl/prj/officeqa
nohup uv run cli bench run --step run >> /tmp/officeqa_bench_run_hybrid.log 2>&1 &
```
Without `--rerun`, this skips the 114 error-free rows and re-runs ONLY the 19 errored ones
(2 network glitches likely succeed; 17 recursion-limit ones may fail again — that is a real
capability ceiling, fine to accept). Takes ~10-30 min. Repeat once if any network errors remain.
- **Do NOT** set `GENAI_GRAPH_DISABLE_NATIVE_INDEX_QUERIES` (we want HNSW/BM25 hybrid).
- **Do NOT** pass `--force` / `--rerun` / `--step build` — the graph is done; `--step run`
  resumes from `runs.jsonl` automatically.

## Expected: native crashes (ladybug 0.16.1 pybind heap corruption)
The process will eventually SIGSEGV (exit 139) or abort (`free(): invalid pointer`, exit 134) —
possibly mid-run, possibly only at teardown. This is the known ladybug bug (see Ladybug issue
draft). Each crash loses at most the ≤6 in-flight questions.

**Crash-resume loop**: just relaunch the exact same command above. `run_questions_flow`
re-loads `runs.jsonl`, skips non-error rows, and continues the remaining questions. Repeat
until the log shows `Completed 133 question run(s)` and the process exits 0.

Monitor:
```bash
pgrep -f 'cli bench run' || echo DEAD
wc -l data/officeqa/glm_5.3_Flash/runs.jsonl
tail -c 600000 /tmp/officeqa_bench_run_hybrid.log | grep -aiE 'SIGSEGV|Aborted|free\(\)|Exit code|failed'
```
(If a resume relaunch reports `Running 0 question(s)`, the run step is done.)

## Next step 2: grade all runs (LLM-as-judge, ~20-40 min)
```bash
cd /home/tcl/prj/officeqa
nohup uv run cli bench run --step grade --rerun > /tmp/officeqa_bench_grade.log 2>&1 &
```
`--rerun` is intentional ONCE here: it re-grades everything so the 2 stale score rows (graded
against old CONTAINS-mode answers) don't pollute the final `scores.jsonl` / `scores_summary.json`.
Outputs: `data/officeqa/glm_5.3_Flash/{scores.jsonl,scores_summary.json}`.

## Next step 3: analysis & reports
1. Analyse `scores.jsonl` (+ `runs.jsonl` trajectories: tool calls, tokens, retrieval patterns,
   failures). Note known data limitation (chart-only data, e.g. UID0056) and the 17
   recursion-limit failures (chart analysis via python_interpreter hitting the 160-step limit).
2. Write a technical report focused on **improvement** (hybrid vs keyword-only retrieval,
   correctness by question type, cost/latency profile) → `report/`.
3. If overall correctness **> 60%**, write a synthesis report modelled on
   `/home/tcl/prj/financebench/report/SYNTHESIS1.md` (exec summary, architecture, performance
   tables, cost profile).

## Misc
- One stale Prefect ephemeral server from a previous session may be listening on port 8996
  (pid ~61330) — safe to kill.
- genai-graph / genai-tk fixes (BAML outline extraction, crash mitigations) are committed &
  pushed (main). officeqa config committed at `4809a38`.
