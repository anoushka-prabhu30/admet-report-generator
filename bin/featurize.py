"""
Featurize compounds from data/compounds.csv using RDKit.
Outputs data/compounds_featurized.csv with physicochemical descriptors
and Morgan fingerprint bits (radius=2, 1024 bits).
"""

import os
import sys
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors, AllChem

IN_PATH  = os.path.join(os.path.dirname(__file__), "..", "data", "compounds.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_featurized.csv")

FP_RADIUS = 2
FP_BITS   = 1024


def lipinski_pass(mw: float, logp: float, hbd: int, hba: int) -> bool:
    return mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10


def featurize_mol(mol) -> dict:
    mw   = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    tpsa = rdMolDescriptors.CalcTPSA(mol)
    nrb  = rdMolDescriptors.CalcNumRotatableBonds(mol)
    hbd  = rdMolDescriptors.CalcNumHBD(mol)
    hba  = rdMolDescriptors.CalcNumHBA(mol)

    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=FP_RADIUS, nBits=FP_BITS)
    fp_arr = np.zeros(FP_BITS, dtype=np.uint8)
    fp_arr[list(fp.GetOnBits())] = 1

    descriptors = {
        "mol_weight":          mw,
        "logp":                logp,
        "tpsa":                tpsa,
        "num_rotatable_bonds": nrb,
        "num_hbd":             hbd,
        "num_hba":             hba,
        "lipinski_pass":       lipinski_pass(mw, logp, hbd, hba),
    }
    fp_cols = {f"fp_{i}": int(fp_arr[i]) for i in range(FP_BITS)}

    return {**descriptors, **fp_cols}


def main():
    if not os.path.exists(IN_PATH):
        print(f"Input file not found: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(IN_PATH)
    print(f"Loaded {len(df)} compounds from {os.path.normpath(IN_PATH)}")

    feature_rows = []
    skipped = []

    for i, row in df.iterrows():
        smiles     = row.get("canonical_smiles")
        chembl_id  = row.get("chembl_id", f"row_{i}")

        if not isinstance(smiles, str) or not smiles.strip():
            print(f"  [SKIP] {chembl_id} — missing SMILES")
            skipped.append((chembl_id, "missing SMILES"))
            continue

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"  [SKIP] {chembl_id} — RDKit could not parse: {smiles[:60]}")
            skipped.append((chembl_id, f"unparseable SMILES: {smiles[:60]}"))
            continue

        features = featurize_mol(mol)
        feature_rows.append({**row.to_dict(), **features})
        print(
            f"  [OK  ] {chembl_id:<20} MW={features['mol_weight']:>7.2f}  "
            f"logP={features['logp']:>5.2f}  "
            f"Lipinski={'PASS' if features['lipinski_pass'] else 'FAIL'}"
        )

    print(f"\nFeaturized: {len(feature_rows)}  |  Skipped: {len(skipped)}")

    if skipped:
        print("\nSkipped compounds:")
        for cid, reason in skipped:
            print(f"  {cid}: {reason}")

    if not feature_rows:
        print("No compounds were featurized.", file=sys.stderr)
        sys.exit(1)

    out_df = pd.DataFrame(feature_rows)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    out_df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(out_df)} rows × {len(out_df.columns)} columns to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
