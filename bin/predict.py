"""
Run ADMET-AI predictions on featurized compounds and append selected
ADMET endpoint columns to the dataset.

Outputs data/compounds_admet.csv.
"""

import os
import sys
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

IN_PATH  = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_featurized.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_admet.csv")

TARGET_ENDPOINTS = [
    "HIA_Hou",                        # human intestinal absorption (classification)
    "BBB_Martini",                    # blood-brain barrier penetration (classification)
    "CYP3A4_Substrate_CarbonMangels", # CYP3A4 substrate (classification)
    "hERG",                           # cardiotoxicity – hERG channel inhibition (classification)
    "DILI",                           # drug-induced liver injury (classification)
    "Caco2_Wang",                     # Caco-2 cell permeability (regression, log cm/s)
]


def load_admet_model():
    print("Loading ADMET-AI models (first run downloads weights, may take a moment)...")
    from admet_ai import ADMETModel  # import late to keep startup fast if it errors
    model = ADMETModel()
    print("Models loaded.\n")
    return model


def predict_batch(model, smiles_list: list[str]) -> pd.DataFrame:
    """Run predictions on a list of SMILES; returns a DataFrame indexed 0..n-1."""
    return model.predict(smiles=smiles_list)


def predict_individually(model, smiles_list: list[str]) -> pd.DataFrame:
    """
    Fall back to one-at-a-time prediction so a single bad molecule
    does not abort the whole batch.
    """
    rows = []
    for smi in smiles_list:
        try:
            result = model.predict(smiles=[smi])
            rows.append(result.iloc[0])
        except Exception as exc:
            print(f"    [WARN] prediction failed for SMILES '{smi[:50]}': {exc}")
            rows.append(pd.Series(dtype=float))
    return pd.DataFrame(rows).reset_index(drop=True)


def select_endpoints(pred_df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the requested endpoints; warn about any that are absent."""
    available = []
    for col in TARGET_ENDPOINTS:
        if col in pred_df.columns:
            available.append(col)
        else:
            # Some builds of admet-ai use slightly different casing / suffixes;
            # try a case-insensitive prefix match as a fallback.
            matches = [c for c in pred_df.columns if c.lower().startswith(col.lower())]
            if matches:
                print(f"  [INFO] '{col}' not found; using '{matches[0]}' instead")
                available.append(matches[0])
            else:
                print(f"  [WARN] endpoint '{col}' not available in this ADMET-AI build — column will be NaN")

    subset = pred_df[available].copy()

    # Re-add any entirely missing target columns as NaN so downstream code
    # can always reference them by the canonical name.
    for col in TARGET_ENDPOINTS:
        if col not in subset.columns:
            subset[col] = np.nan

    return subset[TARGET_ENDPOINTS]


def main():
    if not os.path.exists(IN_PATH):
        print(f"Input file not found: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(IN_PATH)
    print(f"Loaded {len(df)} compounds from {os.path.normpath(IN_PATH)}\n")

    # Separate rows with valid vs missing SMILES.
    has_smiles = df["canonical_smiles"].notna() & (df["canonical_smiles"].str.strip() != "")
    valid_df   = df[has_smiles].copy().reset_index(drop=True)
    invalid_df = df[~has_smiles].copy()

    if invalid_df.shape[0]:
        print(f"[WARN] {invalid_df.shape[0]} rows have no SMILES and will get NaN predictions.\n")

    smiles_list = valid_df["canonical_smiles"].tolist()
    model = load_admet_model()

    # --- attempt batch prediction first ----------------------------------------
    pred_df = None
    print(f"Running batch prediction on {len(smiles_list)} compounds...")
    try:
        pred_df = predict_batch(model, smiles_list)
        print(f"Batch prediction complete ({len(pred_df)} results).\n")
    except Exception as exc:
        print(f"[WARN] Batch prediction failed ({exc}); falling back to per-molecule mode.\n")

    if pred_df is None or len(pred_df) != len(smiles_list):
        print("Running per-molecule predictions...")
        pred_df = predict_individually(model, smiles_list)
        print(f"Per-molecule prediction complete.\n")

    # --- select and align endpoints -------------------------------------------
    endpoint_df = select_endpoints(pred_df)
    endpoint_df.index = valid_df.index   # align with valid_df

    # Attach predictions to the valid rows, then re-join with invalid rows.
    valid_out = pd.concat([valid_df, endpoint_df], axis=1)

    if invalid_df.shape[0]:
        for col in TARGET_ENDPOINTS:
            invalid_df[col] = np.nan
        out_df = pd.concat([valid_out, invalid_df], ignore_index=True)
    else:
        out_df = valid_out

    # --- summary ---------------------------------------------------------------
    print("Prediction summary (valid-SMILES compounds):")
    for col in TARGET_ENDPOINTS:
        col_data = out_df[col].dropna()
        if col_data.empty:
            print(f"  {col:<45} no data")
        elif col == "Caco2_Wang":
            print(f"  {col:<45} mean={col_data.mean():.3f}  min={col_data.min():.3f}  max={col_data.max():.3f}")
        else:
            pos_rate = col_data.mean() * 100
            print(f"  {col:<45} positive rate={pos_rate:.1f}%  (n={len(col_data)})")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out_df)} rows × {len(out_df.columns)} columns to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
