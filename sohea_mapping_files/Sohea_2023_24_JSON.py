from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


# -----------------------------
# Helpers
# -----------------------------
YES_VALUES = {"Y", "YES", "TRUE", "1", "T"}


def clean(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x).strip()


def is_yes(x: Any) -> bool:
    return clean(x).upper() in YES_VALUES


def norm_col_name(name: Any) -> str:
    """
    Normalize headers for matching (underscores vs spaces, casing, etc.).
    Keep pandas suffixes like ".1", ".2".
    """
    s = str(name).strip()
    m = re.match(r"^(.*?)(\.\d+)$", s)
    suffix = m.group(2) if m else ""
    base = m.group(1) if m else s
    base = base.lower().replace("_", " ")
    base = re.sub(r"\s+", " ", base).strip()
    return base + suffix


def tokens(normed: str) -> Set[str]:
    base = re.sub(r"\.\d+$", "", normed)
    return set(base.split())


def find_first_col_idx(norm_cols: List[str], must_have: Set[str], must_not_have: Set[str] = set()) -> Optional[int]:
    for i, c in enumerate(norm_cols):
        t = tokens(c)
        if must_have.issubset(t) and t.isdisjoint(must_not_have):
            return i
    return None


def find_all_child_id_cols(norm_cols: List[str]) -> List[int]:
    """
    Find repeated Child ID columns (Child Ques ID / Child Question ID).
    """
    idxs: List[int] = []
    for i, c in enumerate(norm_cols):
        t = tokens(c)
        if "child" in t and "id" in t and ("question" in t or "ques" in t):
            idxs.append(i)
    return idxs


def node_key(qid: str, qtext: str) -> str:
    """
    Internal identity: prefer ID, fallback to text.
    """
    qid = clean(qid)
    qtext = clean(qtext)
    if qid:
        if re.fullmatch(r"\d+\.0", qid):
            qid = qid[:-2]
        return f"ID:{qid}"
    if qtext:
        return f"TEXT:{qtext}"
    return "UNKNOWN"


def label_from_key(k: str, label_map: Dict[str, str]) -> str:
    lbl = label_map.get(k, "").strip()
    if lbl:
        return lbl
    if k.startswith("TEXT:"):
        return k[5:]
    if k.startswith("ID:"):
        return k[3:]
    return ""


# -----------------------------
# Trigger-code parsing (from Trigger Variable columns)
# -----------------------------
def parse_trigger_codes(cell: Any) -> List[str]:
    """
    Trigger Variable cells are codes like:
      "1,2,3,4" or "3" or "1-4"
    We ONLY extract digits, expand ranges, dedupe.
    """
    # numeric cell
    if isinstance(cell, int) and not isinstance(cell, bool):
        return [str(cell)]
    if isinstance(cell, float) and not pd.isna(cell):
        if abs(cell - round(cell)) < 1e-9:
            return [str(int(round(cell)))]
        return [str(cell)]

    s = clean(cell)
    if not s:
        return []

    s = s.strip().strip("[](){}")
    s = re.sub(r"[\n\r\t;|/]+", ",", s)

    out: List[str] = []

    # expand ranges like 1-4
    for a, b in re.findall(r"\b(\d+)\s*-\s*(\d+)\b", s):
        ia, ib = int(a), int(b)
        step = 1 if ia <= ib else -1
        out.extend([str(i) for i in range(ia, ib + step, step)])

    # remove ranges then extract remaining integers
    s2 = re.sub(r"\b\d+\s*-\s*\d+\b", " ", s)
    out.extend(re.findall(r"\b\d+\b", s2))

    # dedupe preserve order
    seen: Set[str] = set()
    deduped: List[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def sort_codes(codes: Set[str]) -> List[str]:
    def k(x: str):
        return (0, int(x)) if re.fullmatch(r"\d+", x) else (1, x)
    return sorted(codes, key=k)


# -----------------------------
# Detect "Repeated across years" (Column C) indicator
# -----------------------------
def detect_repeated_across_years_col(norm_cols: List[str]) -> Optional[int]:
    """
    Detect Column C header like:
    'repeated across years' (or similar).
    """
    for i, c in enumerate(norm_cols):
        t = tokens(c)
        if {"repeated", "across", "years"}.issubset(t):
            return i
    # fallback: if your header says only "across years"
    for i, c in enumerate(norm_cols):
        t = tokens(c)
        if {"across", "years"}.issubset(t):
            return i
    return None


# -----------------------------
# Build minimal JSON
# -----------------------------
def build_minimal_json(
    df: pd.DataFrame,
    filter_common_yes: bool,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    orig_cols = list(df.columns)
    norm_cols = [norm_col_name(c) for c in orig_cols]

    # FILTER: only "YES" in Column C (Repeated across years)
    if filter_common_yes:
        rep_idx = detect_repeated_across_years_col(norm_cols)
        if rep_idx is None:
            raise ValueError("Could not detect 'Repeated across years' (Column C) indicator column for YES filtering.")
        rep_col = orig_cols[rep_idx]
        df = df[df[rep_col].apply(is_yes)].copy()

        if debug:
            print(f"Applied filter: {rep_col} == YES. Rows after filter = {len(df)}")

    # Parent columns
    parent_q_text_idx = find_first_col_idx(norm_cols, {"parent", "question"}, {"id"})
    if parent_q_text_idx is None:
        parent_q_text_idx = find_first_col_idx(norm_cols, {"parent", "ques"}, {"id"})
    if parent_q_text_idx is None:
        raise ValueError("Could not detect Parent Question column.")

    parent_q_id_idx = find_first_col_idx(norm_cols, {"parent", "id"})
    if parent_q_id_idx is None:
        raise ValueError("Could not detect Parent Question ID / Parent Ques ID column.")

    # Find Parent Response Options
    parent_response_idx = find_first_col_idx(norm_cols, {"parent", "response", "options"})  # **Added this line**


    # Child question text columns
    l1_q_idx = find_first_col_idx(norm_cols, {"child", "question", "l1"})
    if l1_q_idx is None:
        l1_q_idx = find_first_col_idx(norm_cols, {"child", "questions", "l1"})
    if l1_q_idx is None:
        raise ValueError("Could not detect Child Question_l1 column.")

    l2_q_idx = find_first_col_idx(norm_cols, {"child", "question", "l2"})
    if l2_q_idx is None:
        l2_q_idx = find_first_col_idx(norm_cols, {"child", "questions", "l2"})
    if l2_q_idx is None:
        raise ValueError("Could not detect Child Question_l2 column.")

    l3_q_idx = find_first_col_idx(norm_cols, {"child", "question", "l3"})
    if l3_q_idx is None:
        l3_q_idx = find_first_col_idx(norm_cols, {"child", "questions", "l3"})
    if l3_q_idx is None:
        raise ValueError("Could not detect Child Question_l3 column.")

    # Find Child Response Options

    l1_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l1"})
    if l1_response_options_idx is None:
        l1_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l1"})
    if l1_response_options_idx is None:
        raise ValueError("Could not detect Child Response Options_L1 column.")

    l2_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l2"})
    if l2_response_options_idx is None:
        l2_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l2"})
    if l2_response_options_idx is None:
        raise ValueError("Could not detect Child Response Options_L2 column.")
    
    l3_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l3"})
    if l3_response_options_idx is None:
        l3_response_options_idx = find_first_col_idx(norm_cols, {"child", "response", "options", "l3"})
    if l3_response_options_idx is None:
        raise ValueError("Could not detect Child Response Options_L3 column.")

    # Trigger Variable columns (3 occurrences: L1/L2/L3)
    trigger_idxs = []
    for i, c in enumerate(norm_cols):
        t = tokens(c)
        if "trigger" in t and ("variable" in t or "var" in t):
            trigger_idxs.append(i)
    trigger_idxs.sort()

    if len(trigger_idxs) < 1:
        raise ValueError("Could not detect Trigger Variable columns.")
    trig_l1_idx = trigger_idxs[0]
    trig_l2_idx = trigger_idxs[1] if len(trigger_idxs) > 1 else None
    trig_l3_idx = trigger_idxs[2] if len(trigger_idxs) > 2 else None

    # Optional Child ID columns (L1/L2/L3)
    child_id_idxs = find_all_child_id_cols(norm_cols)
    child_id_l1_idx = child_id_idxs[0] if len(child_id_idxs) > 0 else None
    child_id_l2_idx = child_id_idxs[1] if len(child_id_idxs) > 1 else None
    child_id_l3_idx = child_id_idxs[2] if len(child_id_idxs) > 2 else None

    if debug:
        def show(i: Optional[int]) -> str:
            return "<missing>" if i is None else f"{orig_cols[i]} (norm='{norm_cols[i]}')"
        print("Detected columns:")
        print("  Parent Question    :", show(parent_q_text_idx))
        print("  Parent Ques ID     :", show(parent_q_id_idx))
        print("  Parent Response col:", show(parent_response_idx))
        print("  Trigger L1         :", show(trig_l1_idx))
        print("  Trigger L2         :", show(trig_l2_idx))
        print("  Trigger L3         :", show(trig_l3_idx))
        print("  Child Question L1  :", show(l1_q_idx))
        print("  Child Question L2  :", show(l2_q_idx))
        print("  Child Question L3  :", show(l3_q_idx))
        print("  Child Response L1  :", show(l1_response_options_idx))
        print("  Child Response L2  :", show(l2_response_options_idx))
        print("  Child Response L3  :", show(l3_response_options_idx))
        print("  Child ID cols      :", [orig_cols[i] for i in child_id_idxs])

    # label map: internal key -> question text
    label_map: Dict[str, str] = {}

    # label map: internal key -> response description text
    description_map: Dict[str, str] = {}

    # roots: all unique parent questions (order preserved)
    roots: List[str] = []
    seen_roots: Set[str] = set()

    # edges: (parent_key, child_key) -> {"codes": set, "order": first_row_order}
    edges: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def add_edge(p: str, c: str, codes: List[str], order: int) -> None:
        if p == "UNKNOWN" or c == "UNKNOWN":
            return
        if not codes:
            return
        k = (p, c)
        if k not in edges:
            edges[k] = {"codes": set(codes), "order": order}
        else:
            edges[k]["codes"].update(codes)
            edges[k]["order"] = min(edges[k]["order"], order)

    # Read rows (from filtered df if applicable)
    for order, row in enumerate(df.itertuples(index=False), start=0):
        vals = row

        p_text = clean(vals[parent_q_text_idx])
        p_id = clean(vals[parent_q_id_idx])
        p_key = node_key(p_id, p_text)
        p_description = clean(vals[parent_response_idx])  
        if p_key != "UNKNOWN":
            if p_text and not label_map.get(p_key):
                label_map[p_key] = p_text
            if p_key not in seen_roots:
                roots.append(p_key)
                seen_roots.add(p_key)
            if p_description and not description_map.get(p_key):
                description_map[p_key] = p_description  

        # L1
        l1_text = clean(vals[l1_q_idx])
        l1_id = clean(vals[child_id_l1_idx]) if child_id_l1_idx is not None else ""
        l1_key = node_key(l1_id, l1_text)
        l1_description = clean(vals[l1_response_options_idx])  # L1 child description
        if l1_text and l1_key != "UNKNOWN" and not label_map.get(l1_key):
            label_map[l1_key] = l1_text
        if l1_description and l1_key != "UNKNOWN" and not description_map.get(l1_key):
            description_map[l1_key] = l1_description
        trig_l1_codes = parse_trigger_codes(vals[trig_l1_idx])
        add_edge(p_key, l1_key, trig_l1_codes, order)

        # L2
        l2_text = clean(vals[l2_q_idx])
        l2_id = clean(vals[child_id_l2_idx]) if child_id_l2_idx is not None else ""
        l2_key = node_key(l2_id, l2_text)
        l2_description = clean(vals[l2_response_options_idx])  # L2 child description
        if l2_text and l2_key != "UNKNOWN" and not label_map.get(l2_key):
            label_map[l2_key] = l2_text
        if l2_description and l2_key != "UNKNOWN" and not description_map.get(l2_key):
            description_map[l2_key] = l2_description
        if (l2_text or l2_id) and trig_l2_idx is not None:
            trig_l2_codes = parse_trigger_codes(vals[trig_l2_idx])
            add_edge(l1_key, l2_key, trig_l2_codes, order)

        # L3
        l3_text = clean(vals[l3_q_idx])
        l3_id = clean(vals[child_id_l3_idx]) if child_id_l3_idx is not None else ""
        l3_key = node_key(l3_id, l3_text)
        l3_description = clean(vals[l3_response_options_idx])  # L3 child description
        if l3_text and l3_key != "UNKNOWN" and not label_map.get(l3_key):
            label_map[l3_key] = l3_text
        if l3_description and l3_key != "UNKNOWN" and not description_map.get(l3_key):
            description_map[l3_key] = l3_description
        if (l3_text or l3_id) and trig_l3_idx is not None:
            trig_l3_codes = parse_trigger_codes(vals[trig_l3_idx])
            add_edge(l2_key, l3_key, trig_l3_codes, order)

    # adjacency with stable order
    children_map: Dict[str, List[Tuple[str, Set[str], int]]] = defaultdict(list)
    for (p, c), info in edges.items():
        children_map[p].append((c, info["codes"], info["order"]))
    for p in children_map:
        children_map[p].sort(key=lambda t: t[2])

    def clean_description(description: Any) -> str:
        """
        Clean description text by removing tab characters and extra spaces.
        Ensures the input is a string before processing.
        """
        if not isinstance(description, str):
            description = str(description) if description is not None else ""
        return description.replace("\t", "").strip()

    # DFS assemble
    def assemble_levels(p: str, visiting: Set[str]) -> List[Dict[str, Any]]:
        if p in visiting:
            return []
        visiting.add(p)
        out_levels: List[Dict[str, Any]] = []
        for c, codeset, _ord in children_map.get(p, []):
            child_description = []  # Default empty description for child questions
            child_description = clean_description(description_map.get(c, "")).split('\n') 
            child_description = [f"{desc}" for idx, desc in enumerate(child_description)]  # Format as required

            out_levels.append(
                {
                    "level_code": sort_codes(codeset),
                    "childquestion": label_from_key(c, label_map),
                    "level_description": child_description,
                    "levels": assemble_levels(c, visiting),
                }
            )
        visiting.remove(p)
        return out_levels

    # Output minimal JSON
    output: List[Dict[str, Any]] = []
    for r in roots:
        p_description_list = clean_description(description_map.get(r, "")).split('\n') 
        p_description_list = [f"{desc}" for idx, desc in enumerate(p_description_list)]  # Format as required

        output.append(
            {
                "question": label_from_key(r, label_map),
                "level_description": p_description_list,
                "levels": assemble_levels(r, set())
            }
        )
    return output


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--input", required=True, help="Path to Excel .xlsx")
    ap.add_argument("--sheet", default=None, help="Sheet name (optional)")

    # Keep your simple --out usage
    ap.add_argument("--out", required=True, help="Output JSON path")

    # NEW: turn on YES-only filtering (for 2023/2024)
    ap.add_argument(
        "--common-only",
        action="store_true",
        help="Filter to only rows where 'Repeated across years' == YES (2023/2024 requirement).",
    )

    ap.add_argument("--debug", action="store_true", help="Print detected columns and filter info")
    args = ap.parse_args()

    df = pd.read_excel(args.input, sheet_name=args.sheet)
    out = build_minimal_json(df, filter_common_yes=args.common_only, debug=args.debug)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.out} with {len(out)} root question(s).")


if __name__ == "__main__":
    main()


# Command to run 

## For 2024 JSON
## python .\Sohea_2023_24_JSON.py --input "SOHEA hierarchical questions mapping 2023 to 2025.xlsx" --sheet "Final Question Mapping 2024" --out "SOHEA_Questions_mapping_2024.json" --common-only --debug

## For 2023 JSON
## python .\Sohea_2023_24_JSON.py --input "SOHEA hierarchical questions mapping 2023 to 2025.xlsx" --sheet "Final Question Mapping 2023" --out "SOHEA_Questions_mapping_2023.json" --common-only --debug