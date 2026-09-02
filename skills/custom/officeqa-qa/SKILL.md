---
name: officeqa-qa
description: Answer OfficeQA questions across documents (Treasury Bulletins, government reports, financial statistics) by navigating the Document Graph and using web search for external world facts.
---

# OfficeQA Question Answering

You answer complex financial and quantitative questions from U.S. Treasury Bulletins and government financial publications by navigating a Document Graph (Folders → Documents → Markdown sections) and leveraging web search for external real-world disambiguation.

---

## 1. Dynamic Structure Discovery & Domain Acronyms

The outline, section tree, and per-table summaries are **extracted dynamically** into the Document Graph during ingestion. Always use `get_document_toc` to inspect the structure of each bulletin rather than guessing table numbers.

Common Treasury Bulletin domain acronyms to recognize when inspecting TOCs and searching:
- **FFO**: Federal Fiscal Operations (budget receipts, outlays, surplus/deficit actuals vs. Mid-Session Review [MSR] estimates).
- **UST**: Account of the U.S. Treasury (Federal Reserve and operating cash balances).
- **FD**: Federal Debt (public debt outstanding, debt held by the public, statutory debt limit).
- **PDO**: Public Debt Operations (Treasury bill/bond offerings and auction results).
- **OFS**: Ownership of Federal Securities (investor classes, foreign ownership).
- **USCC**: U.S. Currency and Coin Outstanding and in Circulation (denomination breakdowns: $1 to $10,000 bills, coins, per capita circulation).
- **IFS**: International Financial Statistics (U.S. reserve assets, liabilities/claims to foreign official institutions and commercial banks).
- **CM**: Capital Movements (cross-border banking and non-banking claims/liabilities by country).

---

## 2. Tool Routing & Investigation Workflow

### A. External Facts Disambiguation (`web_search`)
Many OfficeQA questions reference external historical events or dates that serve as query parameters:
- *Examples*: "The calendar year Amazon stock reached its lowest point between 2000 and 2005", "The calendar year the U.S. government passed a multi-billion bank bailout package (TARP/EESA)", "The historical bureau merged with Public Debt to form the Bureau of the Fiscal Service".
- **Rule**: Use `web_search` to confirm external dates, years, merger histories, or legislation names **first**, then use those exact years/parameters to navigate the document graph.
- **Do NOT** use `web_search` for internal bulletin data, numbers, or table cells that reside inside the Document Graph.

### B. Document Graph Navigation Loop
1. **Orient with `get_folder_toc()`**:
   - List available documents to select the target bulletin or year.
2. **Explore Outline with `get_document_toc(document_id=<id>, max_level=2)`**:
   - Read the section tree and descriptions to locate the exact section or table for the target metric.
3. **Targeted Search with `search_sections(query="<query>")`**:
   - Use hybrid (vector + BM25) search for specific line items, table codes, or headers.
4. **Read Section Content with `get_section_content(section_ids="<id>")`**:
   - Inspect raw Markdown table rows, column dates, units, and footnote markers.
5. **Map Before Re-Searching**:
   - If searches do not immediately yield the table, inspect `get_document_toc` rather than issuing repeated blind keyword queries.

---

## 3. Grounded Calculation & Answering Rules

- **Scale & Unit Verification**:
  - Always verify whether table values are reported in **thousands of dollars ($ thousands)**, **millions of dollars ($ millions)**, **billions of dollars**, or **exact dollar amounts / piece counts**.
  - Always check column date headers (e.g. *June 30, 2011*, *End of July 2011*, *Fiscal Year 2010*).
- **Calculation Precision & Formulas**:
  - *Weighted Average Denomination*: $\frac{\text{Total Value of Currency in Circulation}}{\text{Total Number of Bills in Circulation}}$ (where number of bills per denomination = $\frac{\text{Value}}{\text{Denomination}}$).
  - *Percentage Point Difference*: Compute ratio $R_1$ and $R_2$ as percentages, then $|\text{Percentage}_2 - \text{Percentage}_1|$.
  - *Geometric Mean*: For $n$ values, $\left(\prod_{i=1}^n x_i\right)^{1/n}$.
  - *R-squared ($R^2$)*: $R^2 = \frac{(S_{xy})^2}{S_{xx} \cdot S_{yy}}$.
  - *Rounding*: Strictly adhere to requested decimal places (e.g., nearest thousandths place = 3 decimal places, hundredths = 2 decimal places, 4 decimal places).
- **Citation & Structure**:
  - Cite section IDs `[hash::sequence]` and source filename.
  - State the concise numeric answer directly first, followed by clear arithmetic steps and table citations.
