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
Many questions reference external real-world events, legislation, inflation series, or corporate dates that serve as query parameters:
- *Examples*: "The calendar year Amazon stock reached its lowest point between 2000 and 2005", "The calendar year the U.S. government passed a multi-billion bank bailout package (TARP/EESA)", "The historical bureau merged with Public Debt to form the Bureau of the Fiscal Service".
- **Rule**: Use `web_search` concisely (1–3 focused queries) to confirm external dates, years, merger histories, or legislation names **first**, then use those exact years/parameters to navigate the document graph.
- **Do NOT** use `web_search` in loops or for internal document data, numbers, or table cells that reside inside the Document Graph.
- **Canonical CPI-U Series Selection**:
  - When adjusting values across calendar years or decades using the Consumer Price Index for All Urban Consumers (CPI-U), **always select the canonical 1913–present CPI-U series (1982–84 = 100)** published by the U.S. Bureau of Labor Statistics (BLS) and the Federal Reserve Bank of Minneapolis.
  - **Do NOT** use pre-1913 / 1800-base estimated historical series unless specifically requested by the question.
- **Statutory Silver Monetary Stock Conversion**:
  - When computing implied physical quantities from Treasury silver monetary stock dollar amounts (or vice versa), use the official U.S. statutory conversion rate of **$1.2929 per fine troy ounce** ($1.292929... / oz, or 0.7734375 oz per nominal dollar).

### B. Document Graph Navigation & Revision Selection
1. **Document Edition and Historical Revision Selection**:
   - When a question references a specific bulletin edition (e.g., "In the September 2011 Treasury Bulletin..."), navigate directly to that document.
   - When querying historical figures for a past year $Y$ (e.g., December 2000) and no specific edition is mandated, **prefer the newest available bulletin/document in the graph that includes year $Y$**, as periodic publications routinely update preliminary estimates with revised final numbers in subsequent editions. If a revision differs from an earlier preliminary report, explicitly state both the revised figure and the earlier report for complete clarity.
2. **Orient with `get_folder_toc()`**:
   - List available documents to select the target bulletin or latest edition covering the requested period.
3. **Explore Outline with `get_document_toc(document_id=<id>, max_level=2)`**:
   - Read the section tree and descriptions to locate the exact section or table for the target metric.
4. **Targeted Search with `search_sections(query="<query>", document_id="<id>")`**:
   - Formulate compact, keyword-focused queries (e.g., `"USCC-1"`, `"Currency in Circulation"`, `"Table FD-1"`, `"Foreign Official Institutions"`).
   - **Do NOT** pass long conversational questions into `search_sections`.
   - Always supply `document_id` when the target bulletin is already known to constrain search scope and eliminate cross-document noise.
5. **Read Section Content with `get_section_content(section_ids="<id>", start_line=..., max_lines=...)`**:
   - Inspect raw Markdown table rows, column dates, units, and footnote markers.
   - **Table Slicing for Tall/Wide Tables**: For tables spanning 50+ lines, pass `start_line` and `max_lines` (e.g. `get_section_content(section_ids="<id>", start_line=1, max_lines=40)`) to inspect header rows and early data, then paginate with subsequent slices to retrieve specific rows without overflowing context.
6. **Map Before Re-Searching**:
   - If searches do not immediately yield the table, inspect `get_document_toc` rather than issuing repeated blind keyword queries.
7. **Multi-Step Continuity & Tool Calling Discipline**:
   - When multi-period, multi-table, or multi-document questions require successive lookups, **ALWAYS invoke the next tool call directly in each turn**.
   - Do NOT output conversational status updates (e.g., *"Now let me check the 1959 bulletin..."*, *"I need to calculate the values..."*) without invoking the tool call, because generating text without tool calls terminates the execution loop and returns the status comment as the final answer.
   - Only emit plain text when you have retrieved all necessary data, completed all calculations via `python_interpreter`, and are ready to deliver your final answer.

---

## 3. Grounded Calculation & Answering Rules

- **Scale & Unit Verification**:
  - Always verify whether table values are reported in **thousands of dollars ($ thousands)**, **millions of dollars ($ millions)**, **billions of dollars**, or **exact dollar amounts / piece counts**.
  - Always check column date headers (e.g. *June 30, 2011*, *End of July 2011*, *Fiscal Year 2010*).
- **Dual-Convention & Formula Clarity**:
  - If a ratio or metric can be interpreted narrowly vs broadly (e.g. liquidity ratio including vs excluding non-marketable liabilities), compute and state both values clearly.
- **Calculation Precision & Python Execution**:
  - Always use `python_interpreter` for non-trivial arithmetic, regressions, transformations, and statistical metrics to eliminate floating-point and rounding errors.
  - Python scripts must include `print(...)` statements to output final computed values.

---

## 4. Python Code & Statistical Formula Templates

Execute these standardized implementations directly in `python_interpreter`:

### A. Ordinary Least Squares (OLS) Linear Regression & Forecasting
Given dependent series $y = [y_0, y_1, \dots, y_{n-1}]$ and independent variable $x = [x_0, x_1, \dots, x_{n-1}]$ (e.g. calendar years $[1990, 1991, \dots]$ or sequential index $[0, 1, \dots]$):
- Model: $y = \text{slope} \cdot x + \text{intercept}$
- Forecasting: $y_{\text{pred}} = \text{slope} \cdot x_{\text{target}} + \text{intercept}$

```python
import numpy as np
from scipy import stats

x = np.array([1990, 1991, 1992, 1993, 1994, 1995, 1996, 1997, 1998], dtype=float)
y = np.array([...], dtype=float)

# Method 1: numpy polyfit (degree 1)
slope, intercept = np.polyfit(x, y, 1)

# Method 2: scipy stats linregress
res = stats.linregress(x, y)
slope, intercept = res.slope, res.intercept

# Prediction
x_target = 1999
y_pred = slope * x_target + intercept
print(f"Slope: {slope:.6f}, Intercept: {intercept:.6f}, Forecast: {y_pred:.6f}")
```

### B. Box-Cox Transformation
For positive values $y > 0$ and transformation parameter $\lambda$:
- If $\lambda \neq 0$: $y^{(\lambda)} = \frac{y^\lambda - 1}{\lambda}$
- If $\lambda = 0$: $y^{(0)} = \ln(y)$

```python
import numpy as np


def box_cox(y, lmbda):
  y = np.asarray(y, dtype=float)
  if lmbda == 0.0:
    return np.log(y)
  return (y**lmbda - 1.0) / lmbda


# Example for lambda = 0.75:
y_val = 54.2
transformed = box_cox(y_val, 0.75)
print(f"Box-Cox (lambda=0.75): {transformed:.6f}")
```

### C. Geometric Mean
For $n$ positive observations $x_1, x_2, \dots, x_n$:
$$\text{Geometric Mean} = \left(\prod_{i=1}^n x_i\right)^{1/n} = \exp\left(\frac{1}{n}\sum_{i=1}^n \ln(x_i)\right)$$

```python
import numpy as np
from scipy import stats

data = np.array([5420.1, 5380.4, 5490.2, 5410.0, 5407.5], dtype=float)

# Method 1: scipy stats gmean
gm = float(stats.gmean(data))

# Method 2: log-sum-exp
gm_alt = float(np.exp(np.mean(np.log(data))))
print(f"Geometric Mean: {gm:.6f}")
```

### D. Inflation Adjustment & Price Indices
- **Adjustment to Base/Target Year Dollars**:
  $$\text{Real Value} = \text{Nominal Value} \times \frac{\text{CPI}_{\text{target}}}{\text{CPI}_{\text{source}}}$$
- **Adjustment via Inflation Rate ($r$)**:
  $$\text{Adjusted Value} = \text{Nominal Value} \times (1 + r) \quad \text{where } r = \frac{\text{CPI}_t - \text{CPI}_{t-1}}{\text{CPI}_{t-1}}$$

```python
# Real value in target-year constant dollars
nominal_val = 2650.0
cpi_source = 14.1  # e.g. 1938 CPI-U
cpi_target = 100.0  # 1982-84 base
real_val = nominal_val * (cpi_target / cpi_source)
print(f"Real Value: {real_val:.4f}")
```

### E. Compound Annual Growth Rate (CAGR)
- **Discrete Annual CAGR** ($n$ periods):
  $$\text{CAGR} = \left(\frac{V_{\text{end}}}{V_{\text{start}}}\right)^{1/n} - 1$$
- **Continuously Compounded Growth Rate**:
  $$r_{\text{continuous}} = \frac{\ln(V_{\text{end}} / V_{\text{start}})}{n}$$

```python
import numpy as np

v_start, v_end, n = 120.0, 240.0, 10
cagr_discrete = (v_end / v_start) ** (1.0 / n) - 1.0
cagr_continuous = np.log(v_end / v_start) / n
print(
    f"Discrete CAGR: {cagr_discrete:.6f}, Continuous CAGR:"
    f" {cagr_continuous:.6f}"
)
```

### F. Realized Variance of Log Rates
For consecutive rate observations $r_1, r_2$:
$$\text{Realized Variance} = \left(\ln(r_2) - \ln(r_1)\right)^2$$

```python
import numpy as np

r1, r2 = 8.50, 7.80
log_diff = np.log(r2) - np.log(r1)
realized_var = log_diff**2
print(f"Realized Variance: {realized_var:.6f}")
```

### G. Gini Coefficient
For a 2-element distribution $[x_1, x_2]$ (e.g. receipts vs expenditures):
$$G = \frac{|x_1 - x_2|}{2(x_1 + x_2)}$$

```python
import numpy as np


def gini(x):
  x = np.asarray(x, dtype=float)
  n = len(x)
  diff_sum = np.sum(np.abs(x[:, None] - x[None, :]))
  return float(diff_sum / (2.0 * n * np.sum(x)))


val = gini([1250.0, 1280.0])
print(f"Gini: {val:.6f}")
```

### H. Weighted Average Denomination
$$\text{Weighted Average} = \frac{\text{Total Value of Currency in Circulation}}{\text{Total Number of Bills in Circulation}} = \frac{\sum V_i}{\sum (V_i / D_i)}$$
where $D_i \in [1, 2, 5, 10, 20, 50, 100, 500, 1000, 5000, 10000]$ and $V_i$ is the dollar value of denomination $D_i$.

---

## 5. Citation & Answer Formatting

- Cite section IDs `[hash::sequence]` and source filename for every extracted metric.
- Format: Present the concise final numerical value directly first, followed by clear arithmetic steps, formula definitions, and table citations.
- Strictly adhere to requested decimal places (e.g., nearest thousandth = 3 decimal places, hundredth = 2 decimal places, tenths = 1 decimal place, whole number = 0 decimal places).
