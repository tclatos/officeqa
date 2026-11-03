# Decision-Model Navigation on OfficeQA Pro — 33-Question Campaign Report

**Date**: 2026-11-03
**Navigator**: `jev@openrouter` (TypeSafe System One, tag `accurate`) via `genai_graph.agent.decision_navigator`
**Synthesizer**: `glm_5.3_Flash@openrouter` (deep agent, `decision` profile)
**Grader**: `DeepSeek-V4-Pro-0813@openrouter` (LLM-as-judge, Mafin 2.5 equivalence rules)
**Subset**: `bench/officeqa_dm_subset.json` — 33 frozen questions (stratified decade × document cardinality)
**Design**: `genai-graph/docs/design/06_decision_model_navigation.md` · Study: `genai-graph/docs/studies/decision_model_navigation.md`

---

## 1. Executive summary

The decision-model navigator is **not yet measurable at full-subset scale**, and the reason is infrastructure, not navigation quality:

| Group | n | decision_fast | baseline (glm_5.3_Flash) |
|---|---|---|---|
| All 33 | 33 | 8 correct / 4 partial — **24.2% strict, 30.3% weighted** | 23 / 4 — 69.7% strict, 75.8% weighted |
| **Runs with a healthy database (0 buffer-pool errors)** | **16** | **8 / 4 — 50% strict, 62.5% weighted** | 11 / 2 — 68.8% strict, **75.0% weighted** |
| Runs degraded by buffer-pool errors | 17 | **0 / 0 — 0%** | 12 / 2 — 76.5% weighted |

**The 17 degraded runs scored exactly zero.** The Ladybug buffer pool failed after ~14 questions, every subsequent graph query raised *"buffer pool is full and no memory could be freed"*, and the agents then had nothing to reason over. The honest headline is therefore the clean split: **62.5% weighted vs 75.0% baseline on the 16 questions that ran on a healthy database — a 12.5-point gap, not 45 points** — at **33% fewer input tokens** (8.23M vs 12.28M) and fewer tool calls.

Cost, whole subset: 452 vs 718 tool calls (−37%), 10.78M vs 20.26M input tokens (**−47%**), navigation itself 375 decision-model calls / 865k tokens / **$0.031 total** (~$0.0009 per question, zero generated tokens).

---

## 2. What ran

`cli bench run -p decision_fast --rerun --skip fetch --skip build -q <33 ids>` then `cli bench grade -p decision_fast`.

Configuration: concurrency 2, `ladybug.buffer_pool_size: 6GB` (read-only), local Python executor, `pack_char_budget: 10000`, `beam_width: 3`, `top_r_sections: 10`, `l2_workers: 1`, per-level confidence gates (L1 0.15 / L2 0.5), `descent_min_confidence: 0.2`, wrap-up 16/24 (extended 24/32), `recursion_limit: 128`, `excluded_tools: [ls, glob, grep]`.

The run was **aborted by the new fail-fast guard after 16 questions** (previously such a run wedged for 2 hours); the 17 remaining tasks had already been submitted and finished during the failure window, which is why all 33 have records.

---

## 3. Failure modes

### 3.1 Infrastructure (dominant: 17 of 33 questions, 249 buffer-pool errors)

Free memory declines monotonically through the run (15 GB → 9 GB) until Ladybug's native allocator fails, after which **every** graph query fails permanently. This is not the connection leak fixed earlier in the campaign (verified: `live=0`, `db_connections=0`, RSS plateau at 1.68 GB over 24 navigations) — the growth is on the agent/LLM side. Pool size only moves the failure point: 8 GB/conc 4 → 17 questions, 4 GB/conc 2 → 26, 6 GB/conc 2 + sequential L2 → ~14.

### 3.2 Answer-quality failures on the healthy 16

| Mode | Questions | Evidence |
|---|---|---|
| **Wrong column / series within a correct table** | UID0001, UID0003, UID0004 | "National defense **and related activities**" $2,779M vs gold $2,602M; summed a *total expenditures* column ($79,920M) instead of national-defense-and-associated-activities ($44,463M). This is exactly the root cause catalogued in `MULTIMODAL_TABLE_RERUN_REPORT.md` §6.1. |
| Empty response after a working session | UID0103 | "returned no numeric values and only reported an empty document graph" |
| Chart reading | UID0030 (degraded set) | line-plot local maxima: answered "fifteen-plus", gold 18 |

**3 of the 4 clean-run losses are the same table-column problem** — a *reading* failure downstream of navigation, not a navigation failure. The navigator put the right table in front of the agent in all three cases.

### 3.3 Gains over baseline (clean set)

UID0005 (incorrect → partial), UID0018 (incorrect → partial), UID0013 (incorrect → partial, 25 calls/884k vs 67/4.03M). On the parity set the navigator also matched baseline on 5/5 with 4 of 5 far cheaper (e.g. UID0015: 8 calls/171k vs 22/409k).

---

## 4. Root causes found and fixed during the campaign

| Finding | Fix |
|---|---|
| One `ladybug.Connection` per question thread kept for the process lifetime (~120 MB each; RSS 151 MB → 3.25 GB over 20 questions) | `release_connection` in `kg.connections` + release in the bench task and in the navigator's L2 workers |
| Absolute 0.5 confidence gate flagged *correct* L1 picks (correct scores measured 0.26–0.77 at L1 vs 0.89–0.96 at L2) | per-level gates (L1 0.15 / L2 0.5) + `descent_min_confidence` |
| `recursion_limit` set *below* the cross-page-extended wrap-up trajectory → runs died before wrap-up could force an answer | wrap-up 16/24 (ext 24/32) with `recursion_limit: 128` |
| Excluding the graph discovery tools left no way to enumerate the corpus when a pack disappointed the agent (answers asked for "a document-listing tool") | restored `get_folder_toc` / `list_documents` / `search_sections`; only `ls`/`glob`/`grep` stay excluded |
| Candidate routing text used `summary or description`; sections have a summary for only 21% of rows at 42 chars avg vs 90% descriptions at 105 chars | `_compose_hint`: edition + description + summary |
| Tool-call-free "plan" narrations ended runs as non-answers | unfinished-narration recovery in `WrapUpMiddleware` |
| Full run records retained in the Prefect result store (~350 MB/question) | compact `RunOutcome` |
| Dead DB retried for hours | fatal-error fail-fast with run abort |
| Navigation traces recorded `scores: {}` | per-level top-k probabilities (`trace_top_k`) |
| Judge merged "declared missing" into `halted_or_empty_response` | rubric distinguishes them |

---

## 5. Recommendations

**P0 — make the benchmark measurable again (blocks everything else).** The remaining growth is on the agent side. Next steps, in order:
1. Instrument per question: process RSS, `gc` object counts, and the sizes of the harness/message histories, plus `nemo_relay`'s trajectory buffers (the ATOF subscriber writes a directory per run — confirm it is not retaining per-run state).
2. Prime suspects: one deep-agent + harness built per question (LLM clients, middleware, skill copies into a fresh `/tmp` workspace per question) not being released; and `langfuse`/OTLP exporters accumulating in memory (the Langfuse container has been restarting all campaign — disable monitoring for bench runs).
3. Short-term mitigation that unblocks measurement today: run the subset in **chunks of ~10 questions per process** (re-launch between chunks) so no single process reaches the failure point, and keep concurrency 2 with a 6 GB pool.

**P1 — attack the table-column reading failure** (3 of 4 clean-run losses). Options, cheapest first:
- Feed the decision model the **table header row** as part of the section candidate text, and/or add a synthesis instruction to echo the exact column header it read before computing.
- Expose the `search_tables` / `get_table_data` tools from `MULTIMODAL_TABLE_RERUN_REPORT.md` §7.1 — note they need a `MarkdownTable` table, which this graph does not have (ingestion gap).
- Use the navigator's L2/L3 scores to **fetch the specific table subsection** rather than the whole section, reducing the chance of reading an adjacent table.

**P2 — close the remaining quality gap on healthy runs.** 62.5% → 75% needs roughly two more questions per 16. Candidates: raise `top_r_sections`/`beam_width` (recall), and a one-shot query decomposition for multi-period questions (the paper's suggestion), measured against the token budget.

**P3 — chart questions.** UID0030/UID0037 remain unanswerable from text; they need the `query_image` VLM path to be reliable (the graph has 0 `Image` rows, so image description at ingestion is another gap).

**P4 — cost work is done, don't regress it.** −47% tokens overall and −33% on the clean subset with a 12.5-pt quality gap is a reasonable trade; any recall increase should be measured against these numbers.

---

## 6. Appendix — clean-run per-question results

| Question | decision | baseline | calls d/b | tokens d/b |
|---|---|---|---|---|
| UID0005 | partial ⬆ | incorrect | 25/32 | 1.26M/1.61M |
| UID0015 | correct = | correct | 11/22 | 260k/409k |
| UID0001 | incorrect ⬇ | correct | 6/33 | 66k/1.30M |
| UID0025 | correct = | correct | 24/30 | 695k/593k |
| UID0103 | incorrect ⬇ | correct | 14/16 | 129k/211k |
| UID0003 | incorrect ⬇ | correct | 18/17 | 312k/298k |
| UID0004 | incorrect ⬇ | partial | 25/34 | 1.06M/1.79M |
| UID0009 | correct = | correct | 11/10 | 144k/89k |
| UID0018 | partial ⬆ | incorrect | 26/21 | 839k/392k |
| UID0022 | correct = | correct | 16/29 | 505k/771k |
| UID0027 | correct = | correct | 9/8 | 311k/150k |
| UID0010 | partial = | partial | 12/10 | 266k/106k |
| UID0017 | correct = | correct | 21/13 | 1.10M/145k |
| UID0013 | partial ⬆ | incorrect | 25/67 | 884k/4.03M |
| UID0007 | correct = | correct | 14/15 | 314k/169k |
| UID0019 | correct = | correct | 6/16 | 88k/215k |

The 17 remaining questions (`UID0068, UID0028, UID0037, UID0055, UID0122, UID0094, UID0030, UID0044, UID0102, UID0077, UID0062, UID0117, UID0039, UID0057, UID0134, UID0073, UID0065`) ran only after the buffer pool failed and are **not** valid measurements; they must be re-run on a healthy process.
