# OfficeQA Benchmark Report — Phase 1: Single-Document Baseline

- **Date**: 2026-09-02 18:15:36 UTC
- **Profile**: `mistral_glm`
- **Agent LLM**: `glm_5.2@openrouter`
- **Build LLM**: `deepseek-v4-flash-0731@openrouter`
- **Judge LLM**: `DeepSeek-V4-Pro-0813@openrouter`
- **Embeddings**: `qwen3_06b@deepinfra` (1024-dim vector index + BM25 FTS)
- **Evaluated Target Document**: `treasury_bulletin_2011_09` (5 benchmark questions)

---

## 1. Summary Metrics

| Metric | Value | Notes |
|---|---|---|
| **Exact Correct** | 2 / 5 (**40.0%**) | 100% of single-document questions answered perfectly |
| **Correct or Partial** | 2 / 5 (**40.0%**) | Strict grading applied |
| **Incorrect** | 3 / 5 (**60.0%**) | All 3 failures caused by multi-bulletin dependency (files not in single-doc graph) |
| **Groundedness Rate** | 4 / 5 (**80.0%**) | Agent correctly cited tables and refused to hallucinate missing bulletins |
| **Numeric Match Rate** | 2 / 5 (**40.0%**) | Exact calculations for single-doc questions |
| **Avg Tool Calls / Question** | 9.6 | Deep agent graph exploration |
| **Avg Input Tokens / Question** | 106,058 | |
| **Avg Output Tokens / Question** | 35,981 | |

---

## 2. Key Findings & Trajectory Analysis

### A. Successes (Single-Document Questions)

1. **`UID0009` — Weighted Average Currency Denomination (June 30, 2011)**:
   - **Task**: Determine the bureau merged with Public Debt to form the Bureau of the Fiscal Service, then calculate the weighted average denomination across all circulating bills from Table USCC-2.
   - **Execution**: Agent called `get_folder_toc` → `get_document_toc` → `get_section_content` on `TABLE USCC-2` and `USCC-1`. Correctly identified Financial Management Service (FMS), extracted value for all 11 bill denominations ($1 to $10,000), calculated total bill count (30,202,172,786 pieces) and total value ($987,708,828,424).
   - **Result**: $\frac{\$987,708,828,424}{30,202,172,786} = 32.703237... \rightarrow \mathbf{32.703}$ (Exact gold match: `32.703`). Judge awarded **Correct / Grounded / Numeric Match**.

2. **`UID0036` — Liquidity Ratio Percentage Point Change**:
   - **Task**: Calculate the absolute percentage point change in U.S. liquidity ratio (marketable liabilities to foreign official institutions) between the Dot-com bubble low (2001) and the 2008 housing crash/bank bailout (2008).
   - **Execution**: Agent identified the relevant calendar years (2001 and 2008), navigated `TABLE IFS-2` (`Selected U.S. Liabilities to Foreigners`), computed the ratio for each year, and calculated the absolute difference: $|15.68\% - 5.79\%| = \mathbf{9.89\%}$ (Exact gold match: `9.89%`). Judge awarded **Correct / Grounded / Numeric Match**.

### B. Failures on Single-File Benchmark Run

All 3 non-perfect questions on the single-file run failed for the same structural reason: **the question requires cross-bulletin longitudinal data from multiple publications**:

1. **`UID0112` ($R^2$ of On-Budget vs. Off-Budget Receipts 1991–2010)**:
   - **Gold Answer**: `0.8298` (requires September 1996, 2001, 2006, and 2011 bulletins).
   - **Behavior**: The agent inspected `TABLE FFO-2`, extracted available 2006–2010 data, computed $R^2 = 0.3458$ for the available subset, and explicitly stated that the remaining 1991–2005 data requires the 1996, 2001, and 2006 bulletins which were absent from the single-document graph.

2. **`UID0155` (Geometric Mean of Reserve Assets across July 2010–2013)**:
   - **Gold Answer**: `29347.01` (requires September 2010, 2011, 2012, and 2013 bulletins).
   - **Behavior**: Agent located `TABLE IFS-1` in the 2011 bulletin, found data only through July 2011, and noted that July 2012 and July 2013 data require the corresponding 2012 and 2013 bulletins.

3. **`UID0204` (MSR Deficit Projection vs. Actual Difference for FY 2010)**:
   - **Gold Answer**: `0.17` (requires September 2010 bulletin for MSR projection and September 2011 bulletin for actuals).
   - **Behavior**: Agent retrieved the actual FY 2010 deficit ($1.29T) from `FFO-1` in the 2011 bulletin, noted that the MSR 2010 estimate resided in the September 2010 bulletin, and refused to guess the missing projection.

---

## 3. Improvement Roadmap for Next Phases

### 1. Ingestion of Full Multi-Bulletin Corpus
- Expand `config/bench.yaml` `files.pathspecs` from `"treasury_bulletin_2011_09*"` to `"treasury_bulletin_*"` (or all 84+ target files).
- Multi-file questions (`UID0112`, `UID0155`, `UID0204`) will then resolve automatically as the agent uses `get_folder_toc` to inspect multiple years.

### 2. Integrated Web Search Tool (`web_search` via Tavily)
- Integrated `create_search_tool` into `OfficeQA QA Analyst` tools.
- Allows the agent to look up external real-world context (historical stock lows, legislation pass dates, agency merger timelines) before navigating the Document Graph.
- Preserves groundedness by keeping document numbers sourced strictly from the graph database.

### 3. Document Decomposition & Slicing Enhancements (Recent Architecture Updates)
Recent updates to **genai-graph** introduced a multi-tier decomposition pipeline that should be leveraged for OfficeQA:
- **Tier 2 Preamble TOC Extraction (`structure_strategy: auto` / `toc_preamble`)**:
  - Treasury Bulletins contain rich printed Tables of Contents in their first 5–10 pages.
  - Using `toc_preamble` extracts structured `DocumentTocPreamble` from the preamble using a fast flash model and anchors headings onto the text body without running the full 100k+ token document through an LLM.
- **Table Formatting & Multi-Page Column Integrity**:
  - Many Treasury Bulletin tables (e.g., `FFO-2` with 46 columns, `USCC-2` denomination listings) span multiple visual pages.
  - Ensuring the Markdown converter preserves markdown table headers and column alignment prevents line wrapping from breaking row/column intersections.
- **Section Slicing & Chunk-Level Indexing (`chunk_size_tokens: 1500`)**:
  - Dense tabular sections can exceed 4,000 tokens.
  - Hybrid indexing with `SectionChunk` embeddings (`qwen3_06b@deepinfra`) and native BM25 full-text search (`section_fts`) ensures that sub-table row searches pinpoint the exact table segment quickly.
- **Decoupled Outline Enrichment (`summaries: true`)**:
  - Separating structural decomposition from section description/summary extraction enables parallel extraction (`workers: 4`) with content-addressed disk caching (`_outlines/`), ensuring fast and reproducible graph builds.

### 4. Agent Domain Skill Specialization (`officeqa-qa`)
- Replaced static table code listings with dynamic outline navigation via `get_document_toc`.
- Added domain-specific calculation guidance (weighted averages, geometric means, percentage point deltas, $R^2$, and unit scale awareness).
- Structured clear rules for when to dispatch to `web_search` (external facts) vs. `search_sections` / `get_section_content` (internal financial tables).
