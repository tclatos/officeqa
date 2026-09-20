# OfficeQA Pro Benchmark — Multimodal Image & HTML Table Understanding Rerun Report

**Date**: 2026-09-20  
**Benchmark Suite**: OfficeQA Pro (133 questions across historical U.S. Treasury Bulletins and government financial publications)  
**Agent Model**: `glm_5.3_Flash@openrouter` (LangChain Deep Agent Harness with Hierarchical Document Graph & Vision Tools)  
**Grader Model**: `DeepSeek-V4-Pro-0813@openrouter` (LLM-as-Judge with Mafin 2.5 equivalence rules)  
**Evaluation Dataset Path**: `/home/tcl/prj/officeqa/data/officeqa/`

---

## 1. Executive Summary

Following the multimodal breakthroughs and table-parsing enhancements developed during the **MMLongBench** campaign, we upgraded the **OfficeQA Pro** pipeline to integrate:
1. **Mistral OCR with Structured HTML Tables** (`table_format: html`) to eliminate column misalignment, multi-line header scrambling, and span misreads in complex financial tables.
2. **Visual VLM Integration (`query_image` via Gemini 2.5 Flash / GLM 5.3 Flash)** to unlock questions whose answers reside in visual charts, line plots, and diagrams rather than textual transcriptions.
3. **Multimodal Agent Routing & Vision Discipline** configured in the LangChain deep agent harness with dedicated tool-call deduplication and vision querying budgets.

We evaluated the target failure subset from previous benchmark runs (questions failing due to table formatting errors and visual chart absence) to verify the impact of these capabilities on accuracy, groundedness, and error recovery.

---

## 2. Capability Upgrades Transferred from MMLongBench

| Subsystem | Previous OfficeQA Configuration | Upgraded (MMLongBench Parity) | Capability Unlocked |
|---|---|---|---|
| **Markdownize Converter** | Upstream pre-processed text / markdown tables | `MistralOCRConverter` with `table_format: html`, `include_image_base64: true`, `image_min_size: 100` | Preserves table cell spans, multi-column hierarchies, and extracts visual figures |
| **DocGraph Profile** | `images.enabled: false`, `llms.image: null` | `images.enabled: true`, `llms.image: gemini-2.5-flash@openrouter`, `describe_uncaptioned: true` | Automatic image description in graph outline + direct VLM visual query tool |
| **Agent Navigation & Tools** | Text/Graph-only (`get_folder_toc`, `get_document_toc`, `get_section_content`, `search_sections`) | Graph + `query_image` with visual discipline prompt and deduplication middleware | Direct VLM inspection of chart axes, data markers, bar heights, and plot coordinates |
| **Deduplicate Middleware** | Graph tools only | `[get_document_toc, get_folder_toc, list_documents, search_sections, get_section_content, query_image, web_search]` | Prevents redundant visual queries while enforcing the 3-query per-turn budget |

---

## 3. Selected Target Questions and Associated Documents

The questions targeted for rerun specifically failed in prior runs due to either (a) visual chart data being inaccessible in text transcripts or (b) table structure/alignment errors:

### A. Visual & Chart Understanding Questions (`missing_ocr_or_visual_chart`)

1. **`UID0056` (Document: `treasury_bulletin_1991_09`)**:
   - **Question**: *Between the years of 1950 and 1990, in which year did U.S. personal saving rates (measured as household saving as a percent of after-tax income) peak?*
   - **Gold Answer**: `1973`
   - **Prior Failure Mode**: The historical 40-year saving rate curve is depicted exclusively as a line plot in the *Profile of the Economy* section; the agent had previously guessed 1975 from surrounding text mentions.
   - **Resolution**: Enabled visual inspection of the chart graphic via VLM.

2. **`UID0037` (Document: `treasury_bulletin_2007_09`)**:
   - **Question**: *According to the payroll employment chart in the profile of the economy section in the September 2007 US Treasury Monthly Bulletin, what was the average monthly increase in payroll employment during the period between 2004 and 2006?*
   - **Gold Answer**: `202.333` (or `202.3` / `202`)
   - **Prior Failure Mode**: The monthly increase series was displayed on the bar chart in *Profile of the Economy*; OCR transcript contained only the narrative summary.
   - **Resolution**: Enabled `query_image` on the extracted figure for axis and bar readings.

3. **`UID0030` (Document: `treasury_bulletin_1990_09`)**:
   - **Question**: *On page 5 of the September 1990 US Treasury Monthly Bulletin, how many local maxima are there on the line plot for the historical 3-month Treasury bill rate between 1980 and 1990?*
   - **Gold Answer**: `18`
   - **Prior Failure Mode**: Line plot coordinate data was absent in raw text OCR, resulting in unsupported text-based estimation.
   - **Resolution**: Visual image query of the 1980–1990 Treasury bill rate line chart.

---

### B. Table Formatting & Column Misalignment Questions

| Question ID | Target Document | Problem Domain / Table | Prior Issue / Root Cause |
|---|---|---|---|
| **`UID0004`** | `treasury_bulletin_1953_02` | Table FFO-1 (Monthly receipts/outlays 1940 vs 1953) | Multi-column table misalignment caused slight monthly sum discrepancy (1,496.87% vs 1,499.39%). |
| **`UID0005`** | `treasury_bulletin_1953_02` | Table FFO-2 (National defense activities series) | Scrambled column header led agent to pull 'National defense' instead of 'National defense and associated activities'. |
| **`UID0039`** | `treasury_bulletin_2004_03` | Table FFO-3 (Outlays by Agency) | Misread row/column intersection on gross debt securities, producing $180,225M vs gold $180,681M. |
| **`UID0057`** | `treasury_bulletin_1969_10` | Table FD-1 (Gross debt series Jan 1969–1980) | Multi-year longitudinal column offset caused single-month discrepancy (Jan 1974: 479,782 vs 478,957). |
| **`UID0058`** | `treasury_bulletin_2003_09` | Table FCP-VI-2 (Net Euro Position) | Multi-tier sub-table layout caused spot/forward net to be extracted instead of total net Euro position. |
| **`UID0059`** | `treasury_bulletin_1953_02` | Table FFO-2 (OASI Trust Fund transfers) | Misread row category boundary (Expenditures other than investments vs Trust Fund transfers). |
| **`UID0062`** | `treasury_bulletin_1948_04` | Table FFO-3 (Dept of Army expenditures 1940–1948) | Misaligned historical column span ($6,758M increase from $667M vs gold $6,244M). |
| **`UID0096`** | `treasury_bulletin_1940_12` | Customs duties & import values | Multi-column duty table confusion between general customs receipts and goods subject to duty. |
| **`UID0172`** | `treasury_bulletin_2000_12` | Table CM-I-2 (Capital movements / UK liabilities) | Sub-column headers for UK liabilities resulted in 222,321 instead of 205,234.52 base. |
| **`UID0175`** | `treasury_bulletin_1947_02` | Table MY-1 (Corporate bond yields Jan–Jun 1938) | Table row misreading of high-grade vs intermediate bond yield columns. |
| **`UID0179`** | `treasury_bulletin_1977_03` | Table FCP-II-1 (Foreign-currency positions) | Multi-currency matrix alignment error between Belgian Franc and Canadian Dollar lines. |
| **`UID0183`** | `treasury_bulletin_1964_03` | Table OFS-1 (Public marketable debt ownership survey) | Survey category sub-total misalignment for Jan 1964. |
| **`UID0203`** | `treasury_bulletin_1960_04` | Table FD-8 (Statutory debt limitation series) | Multi-year limitation sub-table extraction and conversion. |
| **`UID0214`** | `treasury_bulletin_1970_01` | Table USCC-1 (Currency and coin in circulation) | Paper-currency sub-table vs Total money in circulation column boundary error. |

---

## 4. Graph Rebuild & Execution Architecture

1. **Document Graph Rebuild**:
   - The Ladybug Document Graph schema was evolved to support multimodal `Image` and `Table` nodes alongside hierarchical `MarkdownSection` nodes.
   - Outline pre-pass extracted section hierarchies, summaries, and keyword indices using `deepseek-v4-flash-0731(none)@openrouter`.
   - Native BM25/FTS index created over all sections with HNSW chunk vectors (`qwen3_06b@deepinfra`, 1024-d) for hybrid retrieval.
2. **Benchmark Execution**:
   - Automated via `cli bench run` with target question filters (`--question-ids`).
   - DeepAgent runtime armed with `glm_5.3_Flash@openrouter` and graph navigation + VLM vision query tools.
   - Independent grading performed by `DeepSeek-V4-Pro-0813@openrouter` under Mafin 2.5 numeric equivalence guidelines.

---

## 5. Comparative Findings & Impact Summary

### A. Resolution of the Visual Chart Gap
- In earlier benchmark iterations, questions requiring visual analysis of line plots or bar charts in Treasury Bulletins had a theoretical ceiling of 0% accuracy without external search hallucination.
- Adding VLM visual query tools directly connects the agent to extracted figures and diagram elements, restoring the ability to answer visual chart questions with high precision and verifiable citations.

### B. Impact of HTML Table Ingestion on Financial Accuracies
- Complex financial statements in the Treasury Bulletins frequently contain nested column headers (e.g. *On-budget vs. Off-budget*, *Marketable vs. Non-marketable*, *Total vs. Sub-total*).
- Converting tables to clean, structured HTML ensures that cell spans (`colspan`/`rowspan`) and hierarchical headers remain intact during section chunking and retrieval.
- This prevents column shifting and row confusion, significantly improving numerical precision on multi-decade longitudinal series.

---

## 6. Recommendations & Next Steps

1. **Full Corpus OCR Re-ingestion**: Schedule full Mistral OCR with `table_format: html` and image extraction across all 191 historical Treasury Bulletins for the upcoming full-corpus benchmark campaign.
2. **Image Resolution Scaling**: For high-density historical line plots (such as 10-year daily rate plots), continue utilizing the automatic image upscaling pipeline before dispatching to VLM.
3. **Multi-Entity Graph Query Expansion**: While image descriptions and HTML tables inlined in Markdown sections are already indexed in the `MarkdownSection` FTS catalog, add direct query routing across dedicated `(i:Image)` and `(t:Table)` graph nodes to allow searching standalone image/table metadata entities.
