---
name: decision-navigation
description: Evidence-pack-first answering loop for decision-model-navigated runs — navigate_folder first, refine with hints (max 2 re-navigations), fall back to graph tools only on low confidence.
---

# Decision-Model Navigation Discipline

Navigation over the Document Graph is performed by a **decision model** (no LLM,
zero generated tokens): each `navigate_folder(query)` call jointly scores every
document and then every section of the top documents, fetching the best sections'
full text as an **evidence pack** with per-section relevance scores.

## The loop

1. **Navigate first.** Pass the user's question VERBATIM as `query` — the decision
   model scores semantic relevance, not keywords. Never pre-shred the question into
   keywords.
2. **Read the pack.** The result contains the selected sections with ids
   `[hash::sequence]`, source document names, and scores. Extract the needed
   numbers directly from the pack.
3. **Refine at most twice.** If the pack is missing something, call
   `navigate_folder` again with `hints` describing precisely what is missing
   (e.g. "need the December 1953 USCC-1 denomination table"). Hard limit: 2
   re-navigation calls per question.
4. **Over-budget sections are pointers, not omissions.** Sections listed with
   "[text omitted: N chars over pack budget]" were selected but not inlined — fetch
   exactly those with `get_section_content(section_ids=...)`. Never re-read an evicted
   pack through `read_file`; that multiplies tokens per page.
5. **Fall back to the graph tools when the pack is insufficient.** If the pack (still)
   reports `low_confidence: true`, `navigation failed`, or simply does not contain the
   table you need, navigate yourself with the classic loop: `list_documents` /
   `get_folder_toc` → `get_document_toc` → `get_section_content` (and `search_sections`
   with 2–3 keywords). Re-navigating with `hints` is the cheapest recovery, but never
   refuse to answer just because the pack was thin — the graph tools are always available.
6. **Visual questions**: figure/chart data is not in section text. Locate the
   candidate section (pack or one TOC pass) and use `query_image` on the referenced
   image early (budget: max 3 calls).
7. Then follow the `officeqa-qa` skill for units, formulas, `python_interpreter`
   arithmetic and citations.

## Trace footer

Every pack ends with a `[[navigation-trace]]` JSON footer (decision-model calls,
tokens, cost, per-level scores, `low_confidence` / `unanswerable` flags). Read the
flags: `unanswerable: true` means the navigator judged the corpus cannot answer the
question — verify via fallback tools before declaring the information absent.
