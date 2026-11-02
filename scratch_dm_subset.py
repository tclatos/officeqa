"""Freeze the stratified OfficeQA Pro subset for the decision-navigation comparison.

Stratifies all OfficeQA Pro questions by decade (of the primary document) and
source_files cardinality (1 vs >=2 documents), then samples round-robin across
strata to 33 questions (~25% of 133), guaranteeing the known-hard multi-period
item UID0005. Output: bench/officeqa_dm_subset.json (frozen, ordered id list +
strata metadata). Deterministic: stable sort, no randomness.
"""

from __future__ import annotations

import json
from collections import OrderedDict, defaultdict
from pathlib import Path

import pandas as pd

N_SUBSET = 33
FORCE_INCLUDE = {"UID0005"}
PARQUET = Path("data/officeqa/officeqa_pro.parquet")
OUT = Path("bench/officeqa_dm_subset.json")


def doc_stem(source_files: str) -> str:
    first = source_files.strip().splitlines()[0].strip()
    return Path(first).stem if first.endswith((".txt", ".pdf", ".md")) else first


def decade_of(doc_stem_str: str) -> str:
    parts = doc_stem_str.split("_")
    year = next((int(p) for p in parts if p.isdigit() and len(p) == 4), None)
    return f"{(year // 10) * 10}s" if year else "unknown"


def main() -> None:
    df = pd.read_parquet(PARQUET)
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        uid = str(row.get("uid") or row.get("officeqa_id") or row.get("id"))
        sources = row.get("source_files")
        stems = [s for s in (str(sources).splitlines() if isinstance(sources, str) else []) if s.strip()]
        primary = doc_stem(sources) if stems else "unknown"
        rows.append(
            {
                "uid": uid,
                "decade": decade_of(primary),
                "n_docs": "1" if len(stems) <= 1 else "2+",
                "question": str(row.get("question", "")),
                "difficulty": str(row.get("difficulty", "")) if pd.notna(row.get("difficulty")) else "",
            }
        )

    strata: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        strata[f"{r['decade']}|{r['n_docs']}"].append(r)
    for members in strata.values():
        members.sort(key=lambda r: r["uid"])

    # Round-robin across strata (largest first for stable coverage), no randomness.
    strata_order = sorted(strata.values(), key=lambda m: (-len(m), m[0]["uid"]))
    picked: "OrderedDict[str, dict[str, str]]" = OrderedDict()
    for uid in FORCE_INCLUDE:
        match = next((r for r in rows if r["uid"] == uid), None)
        if match:
            picked[uid] = match
    progress = 0
    while len(picked) < N_SUBSET:
        added = False
        for members in strata_order:
            if progress < len(members) and members[progress]["uid"] not in picked:
                picked[members[progress]["uid"]] = members[progress]
                if len(picked) >= N_SUBSET:
                    break
                added = True
        if not added:
            progress += 1
            continue
        progress += 1

    subset = list(picked.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "description": "Frozen stratified OfficeQA Pro subset for the decision-model navigation comparison "
                "(docs/studies/decision_model_navigation.md §4.2): 33/133 questions, stratified by "
                "decade × source_files cardinality, incl. the hard multi-period UID0005.",
                "n": len(subset),
                "question_ids": [r["uid"] for r in subset],
                "strata": {r["uid"]: f"{r['decade']}|{r['n_docs']}" for r in subset},
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    by_stratum: dict[str, int] = defaultdict(int)
    for r in subset:
        by_stratum[f"{r['decade']}|{r['n_docs']}"] += 1
    print(f"Froze {len(subset)} questions to {OUT}")
    for k in sorted(by_stratum):
        print(f"  {k}: {by_stratum[k]}")


if __name__ == "__main__":
    main()
