"""Eligibility engine for NidhiFinder.

Loads a scheme dataset (CSV or Excel) with pandas, cleans it into a standard
shape, and matches a citizen profile against every scheme.

This module has no Streamlit imports, so it can be tested on its own.

Dataset format (one row per scheme)
-----------------------------------
Required columns : name_en, url
Optional columns : name_hi, benefit_en, benefit_hi,
                   min_age, max_age, max_income,
                   genders, states, areas, occupations, categories, education,
                   disability_required, bpl_required, land_required,
                   minority_required

* Leave a cell empty (or write "All") to mean "no restriction".
* Put several allowed values in one cell separated by |   e.g.  SC/ST|OBC
* The *_required columns take Yes / No.
"""
from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = ["name_en", "url"]
TEXT_COLUMNS = ["name_en", "name_hi", "benefit_en", "benefit_hi", "url"]
NUMERIC_COLUMNS = ["min_age", "max_age", "max_income"]
LIST_COLUMNS = ["genders", "states", "areas", "occupations", "categories", "education"]
FLAG_COLUMNS = ["disability_required", "bpl_required", "land_required", "minority_required"]

# dataset column -> key in the citizen profile
LIST_FIELD_TO_PROFILE = {
    "genders": "gender",
    "states": "state",
    "areas": "area",
    "occupations": "occupation",
    "categories": "category",
    "education": "education",
}
FLAG_TO_PROFILE = {
    "disability_required": "disability",
    "bpl_required": "bpl",
    "land_required": "land",
    "minority_required": "minority",
}


# --------------------------------------------------------------------------
# Loading and cleaning (pandas)
# --------------------------------------------------------------------------
def read_dataset(source, filename: str | None = None) -> pd.DataFrame:
    """Read a CSV or Excel file (path or file-like object) into a raw DataFrame."""
    name = (filename or getattr(source, "name", str(source))).lower()
    if hasattr(source, "seek"):
        source.seek(0)
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(source, dtype=str, keep_default_na=False)
    if name.endswith(".csv"):
        # utf-8-sig also handles CSVs saved from Excel (Hindi text stays intact)
        return pd.read_csv(source, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    raise ValueError("Unsupported file type. Please use a .csv or .xlsx file.")


def _split_values(cell) -> list[str]:
    items = [x.strip() for x in str(cell).replace(";","|").split("|") if x.strip()]
    if any(i.lower() == "all" for i in items):
        return []  # empty list = no restriction
    return items


def normalize_dataset(raw: pd.DataFrame) -> pd.DataFrame:
    """Validate columns, fill defaults and convert types."""
    df = raw.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("missing required column(s): " + ", ".join(missing))

    for col in TEXT_COLUMNS + LIST_COLUMNS + FLAG_COLUMNS + NUMERIC_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    # Drop blank rows, then fall back to English text where Hindi is missing
    df = df[df["name_en"] != ""].reset_index(drop=True)
    df["name_hi"] = df["name_hi"].where(df["name_hi"] != "", df["name_en"])
    df["benefit_hi"] = df["benefit_hi"].where(df["benefit_hi"] != "", df["benefit_en"])

    # Numbers (blank -> NaN, which we treat as "no limit")
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["min_age"] = df["min_age"].fillna(0)
    df["max_age"] = df["max_age"].fillna(120)

    # Multi-value columns -> Python lists
    for col in LIST_COLUMNS:
        df[col] = df[col].apply(_split_values)

    # Yes/No columns -> booleans
    for col in FLAG_COLUMNS:
        df[col] = df[col].str.lower().isin(["yes", "y", "true", "1"])

    return df


def collect_values(df: pd.DataFrame, column: str) -> list[str]:
    """All distinct values used in a list column (to extend the form options)."""
    return sorted({v for items in df[column] for v in items})


def to_display(df: pd.DataFrame) -> pd.DataFrame:
    """A readable copy of the dataset (lists joined with | ) for previews."""
    out = df.copy()
    for col in LIST_COLUMNS:
        out[col] = out[col].apply(" | ".join)
    return out


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------
def reasons_for(scheme: dict, profile: dict) -> list[tuple[str, dict]]:
    """Return why the person does NOT qualify. An empty list means eligible."""
    reasons: list[tuple[str, dict]] = []

    if not scheme["min_age"] <= profile["age"] <= scheme["max_age"]:
        reasons.append(("age", {"min": int(scheme["min_age"]), "max": int(scheme["max_age"])}))

    if pd.notna(scheme["max_income"]) and profile["income"] > scheme["max_income"]:
        reasons.append(("income", {"max": int(scheme["max_income"])}))

    for col, key in LIST_FIELD_TO_PROFILE.items():
        allowed = scheme[col]
        if allowed and str(profile[key]).casefold() not in {a.casefold() for a in allowed}:
            reasons.append(("list", {"field": key, "allowed": allowed}))

    for col, key in FLAG_TO_PROFILE.items():
        if scheme[col] and not profile[key]:
            reasons.append((f"flag_{key}", {}))

    return reasons


def evaluate(df: pd.DataFrame, profile: dict):
    """Split schemes into (eligible, rejected). Each item is (scheme_dict, reasons)."""
    eligible, rejected = [], []
    for scheme in df.to_dict("records"):
        reasons = reasons_for(scheme, profile)
        (rejected if reasons else eligible).append((scheme, reasons))
    return eligible, rejected


def format_inr(n) -> str:
    """Indian digit grouping: 250000 -> 2,50,000"""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])
