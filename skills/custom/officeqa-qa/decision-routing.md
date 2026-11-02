# Decision-Model Routing Context (Treasury Bulletins)

This excerpt carries the **navigation** knowledge of the `officeqa-qa` skill. It is
injected verbatim into the decision model's shared state so the model can score
which documents / sections are relevant. It is routing knowledge only — statistical
formulas and citation rules stay on the synthesis side.

## Document types & domain acronyms

The corpus is U.S. Treasury Bulletins and government financial publications across
nine decades. Candidate sections may be labeled with these acronyms:

- **FFO**: Federal Fiscal Operations (budget receipts, outlays, surplus/deficit actuals vs. Mid-Session Review [MSR] estimates).
- **UST**: Account of the U.S. Treasury (Federal Reserve and operating cash balances).
- **FD**: Federal Debt (public debt outstanding, debt held by the public, statutory debt limit).
- **PDO**: Public Debt Operations (Treasury bill/bond offerings and auction results).
- **OFS**: Ownership of Federal Securities (investor classes, foreign ownership).
- **USCC**: U.S. Currency and Coin Outstanding and in Circulation (denomination breakdowns: $1 to $10,000 bills, coins, per capita circulation).
- **IFS**: International Financial Statistics (U.S. reserve assets, liabilities/claims to foreign official institutions and commercial banks).
- **CM**: Capital Movements (cross-border banking and non-banking claims/liabilities by country).

A question asking about "saving rates", "receipts by source", "debt outstanding",
"currency in circulation", "gold stock", or "foreign holdings" maps to the
corresponding table family above (e.g. Table FFO-1, FD-1, USCC-1, IFS-…).

## Edition & revision selection

- When a question references a specific bulletin edition (e.g. "In the September 2011
  Treasury Bulletin..."), that document is the target — date/period in a document's
  filename (e.g. `treasury_bulletin_2011_09`) identifies the edition.
- When querying historical figures for a past year and no specific edition is
  mandated, the **newest available bulletin that includes that year** is the right
  target: periodic publications revise preliminary estimates in later editions.
- Bulletin issues are monthly; a document's filename embeds its publication year and
  month. Data for a period is usually reported in issues published shortly after
  that period (or in a special annual edition).
- Figures are often revised in later bulletins — locate the specific month/year
  edition requested, otherwise prefer the latest revision covering the target year.
