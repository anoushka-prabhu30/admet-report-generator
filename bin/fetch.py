"""
Fetch 50 FDA-approved small molecule drugs from ChEMBL and save to data/compounds.csv.
Uses the ChEMBL REST API directly with paginated requests to avoid server-side OOM errors.
"""

import os
import sys
import requests
import pandas as pd

TARGET_COUNT = 50
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "compounds.csv")
BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
PAGE_SIZE = 50


def fetch_compounds(target: int = TARGET_COUNT) -> pd.DataFrame:
    rows = []
    fetched = 0
    skipped = 0
    offset = 0

    print("Querying ChEMBL for FDA-approved small molecule drugs (max_phase=4)...")

    while fetched < target:
        params = {
            "max_phase": 4,
            "molecule_type": "Small molecule",
            "limit": PAGE_SIZE,
            "offset": offset,
        }

        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        molecules = data.get("molecules", [])
        if not molecules:
            break

        for compound in molecules:
            if fetched >= target:
                break

            structures = compound.get("molecule_structures") or {}
            props = compound.get("molecule_properties") or {}

            chembl_id = compound.get("molecule_chembl_id")
            pref_name = compound.get("pref_name")
            smiles = structures.get("canonical_smiles")
            mw = props.get("full_mwt")
            alogp = props.get("alogp")

            if not smiles or mw is None or alogp is None:
                skipped += 1
                continue

            rows.append(
                {
                    "chembl_id": chembl_id,
                    "pref_name": pref_name,
                    "canonical_smiles": smiles,
                    "molecular_weight": mw,
                    "alogp": alogp,
                }
            )
            fetched += 1
            print(f"  [{fetched:>3}] {chembl_id} — {pref_name or 'unnamed'}")

        if not data.get("page_meta", {}).get("next"):
            break

        offset += PAGE_SIZE

    print(f"\nDone. Fetched: {fetched}  |  Skipped (missing fields): {skipped}")
    return pd.DataFrame(rows)


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    df = fetch_compounds()

    if df.empty:
        print("No compounds retrieved — check your network or ChEMBL API status.", file=sys.stderr)
        sys.exit(1)

    df.to_csv(OUT_PATH, index=False)
    print(f"Saved {len(df)} compounds to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
