"""
Generate output/report.html from data/compounds_narrated.csv.
Each compound gets a Plotly radar chart, a colour-coded risk table, and a Groq memo.
A summary table at the top ranks all compounds by overall ADMET score.
"""

import os
import sys
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from jinja2 import Environment, FileSystemLoader

IN_PATH       = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_narrated.csv")
OUT_PATH      = os.path.join(os.path.dirname(__file__), "..", "output", "report.html")
TEMPLATE_DIR  = os.path.join(os.path.dirname(__file__), "..", "templates")
TEMPLATE_FILE = "report.html.j2"

ADMET_COLS = [
    "HIA_Hou",
    "BBB_Martini",
    "CYP3A4_Substrate_CarbonMangels",
    "hERG",
    "DILI",
    "Caco2_Wang",
]

RADAR_LABELS = {
    "HIA_Hou":                        "HIA",
    "BBB_Martini":                    "BBB",
    "CYP3A4_Substrate_CarbonMangels": "CYP3A4",
    "hERG":                           "hERG",
    "DILI":                           "DILI",
    "Caco2_Wang":                     "Caco-2",
}

PROP_DESCRIPTIONS = {
    "HIA_Hou":                        "Human Intestinal Absorption",
    "BBB_Martini":                    "Blood-Brain Barrier Penetration",
    "CYP3A4_Substrate_CarbonMangels": "CYP3A4 Substrate",
    "hERG":                           "hERG Cardiotoxicity",
    "DILI":                           "Drug-Induced Liver Injury",
    "Caco2_Wang":                     "Caco-2 Permeability (log cm/s)",
}


# ---------------------------------------------------------------------------
# Normalisation & scoring
# ---------------------------------------------------------------------------

def minmax_norm(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return series.map(lambda x: 0.5 if pd.notna(x) else np.nan)
    return (series - lo) / (hi - lo)


def compute_admet_score(row: pd.Series) -> float:
    """Higher = better candidate (rewards absorption, penalises toxicity)."""
    pairs = [
        ("HIA_Hou",         False),
        ("Caco2_Wang_norm", False),
        ("hERG",            True),
        ("DILI",            True),
        ("CYP3A4_Substrate_CarbonMangels", True),
    ]
    vals = []
    for col, invert in pairs:
        v = row.get(col)
        if pd.notna(v):
            vals.append(1 - float(v) if invert else float(v))
    return round(float(np.mean(vals)), 4) if vals else np.nan


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def risk_class(col: str, val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "na"
    v = float(val)
    if col == "HIA_Hou":
        return "green" if v >= 0.7 else "yellow" if v >= 0.4 else "red"
    if col == "BBB_Martini":
        return "green" if v < 0.3 else "yellow" if v < 0.7 else "red"
    if col in ("hERG", "DILI"):
        return "green" if v < 0.3 else "yellow" if v < 0.5 else "red"
    if col == "CYP3A4_Substrate_CarbonMangels":
        return "green" if v < 0.5 else "yellow" if v < 0.7 else "red"
    if col == "Caco2_Wang":
        return "green" if v > -5.0 else "yellow" if v > -6.0 else "red"
    return "na"


def risk_label(col: str, val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    v = float(val)
    lookup = {
        "HIA_Hou": [
            ("High absorption",  v >= 0.7),
            ("Moderate",         v >= 0.4),
            ("Low absorption",   True),
        ],
        "BBB_Martini": [
            ("Low penetration",  v < 0.3),
            ("Moderate",         v < 0.7),
            ("High penetration", True),
        ],
        "hERG": [
            ("Low risk",   v < 0.3),
            ("Moderate",   v < 0.5),
            ("High risk",  True),
        ],
        "DILI": [
            ("Low risk",   v < 0.3),
            ("Moderate",   v < 0.5),
            ("High risk",  True),
        ],
        "CYP3A4_Substrate_CarbonMangels": [
            ("Unlikely",  v < 0.5),
            ("Moderate",  v < 0.7),
            ("Likely",    True),
        ],
        "Caco2_Wang": [
            ("High perm.",    v > -5.0),
            ("Moderate",      v > -6.0),
            ("Low perm.",     True),
        ],
    }
    for label, condition in lookup.get(col, []):
        if condition:
            return label
    return f"{v:.3f}"


# ---------------------------------------------------------------------------
# Radar chart
# ---------------------------------------------------------------------------

def make_radar(norm_vals: dict, name: str) -> str:
    labels = list(norm_vals.keys())
    values = [float(norm_vals[l]) if pd.notna(norm_vals[l]) else 0.0 for l in labels]
    # close polygon
    r      = values + [values[0]]
    theta  = labels + [labels[0]]

    fig = go.Figure(go.Scatterpolar(
        r=r, theta=theta,
        fill="toself",
        fillcolor="rgba(33, 97, 200, 0.15)",
        line=dict(color="rgba(33, 97, 200, 0.9)", width=2),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="white",
            radialaxis=dict(visible=True, range=[0, 1], tickfont=dict(size=9), gridcolor="#e0e0e0"),
            angularaxis=dict(tickfont=dict(size=11, color="#333")),
        ),
        showlegend=False,
        margin=dict(l=55, r=55, t=25, b=25),
        height=310,
        paper_bgcolor="white",
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(IN_PATH):
        print(f"Input file not found: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(IN_PATH)
    print(f"Loaded {len(df)} compounds from {os.path.normpath(IN_PATH)}")

    # Add normalised Caco2 for scoring and radar
    df["Caco2_Wang_norm"] = minmax_norm(df["Caco2_Wang"].fillna(df["Caco2_Wang"].median()))
    df["admet_score"]     = df.apply(compute_admet_score, axis=1)

    # --- summary table (sorted by score) -----------------------------------
    ranked = df.sort_values("admet_score", ascending=False).reset_index(drop=True)
    ranked.index += 1

    summary_rows = []
    for rank, row in ranked.iterrows():
        score = row["admet_score"]
        summary_rows.append({
            "rank":      rank,
            "chembl_id": row.get("chembl_id", ""),
            "name":      row.get("pref_name") or row.get("chembl_id", f"cpd_{rank}"),
            "score":     f"{score:.3f}" if pd.notna(score) else "N/A",
            "score_pct": int(score * 100) if pd.notna(score) else 0,
            "cells":     {
                col: {
                    "value": f"{row[col]:.3f}" if pd.notna(row.get(col)) else "N/A",
                    "cls":   risk_class(col, row.get(col)),
                }
                for col in ADMET_COLS
            },
        })

    # --- per-compound data -------------------------------------------------
    print("Generating radar charts and risk tables...")
    compounds_data = []
    for i, row in df.iterrows():
        name      = row.get("pref_name") or row.get("chembl_id", f"compound_{i}")
        chembl_id = row.get("chembl_id", "")

        norm_vals = {}
        for col in ADMET_COLS:
            label = RADAR_LABELS[col]
            if col == "Caco2_Wang":
                norm_vals[label] = row.get("Caco2_Wang_norm", np.nan)
            else:
                norm_vals[label] = row.get(col, np.nan)

        risk_rows = [
            {
                "property":  PROP_DESCRIPTIONS[col],
                "short":     RADAR_LABELS[col],
                "value":     f"{row[col]:.3f}" if pd.notna(row.get(col)) else "N/A",
                "cls":       risk_class(col, row.get(col)),
                "label":     risk_label(col, row.get(col)),
            }
            for col in ADMET_COLS
        ]

        score = row.get("admet_score")
        memo  = row.get("groq_memo", "")

        compounds_data.append({
            "name":       name,
            "chembl_id":  chembl_id,
            "score":      f"{score:.3f}" if pd.notna(score) else "N/A",
            "score_pct":  int(score * 100) if pd.notna(score) else 0,
            "chart_html": make_radar(norm_vals, name),
            "risk_rows":  risk_rows,
            "memo":       memo if isinstance(memo, str) and memo.strip() else None,
        })
        print(f"  [{i+1:>3}] {chembl_id} — {name}")

    # --- render template ---------------------------------------------------
    env      = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    template = env.get_template(TEMPLATE_FILE)
    html     = template.render(
        summary_rows   = summary_rows,
        compounds      = compounds_data,
        total          = len(df),
        admet_cols     = ADMET_COLS,
        radar_labels   = RADAR_LABELS,
        prop_desc      = PROP_DESCRIPTIONS,
    )

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nReport written to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
