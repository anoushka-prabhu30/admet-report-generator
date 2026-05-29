"""
Generate a 3-sentence drug-candidate memo for each compound using Groq.
Reads  data/compounds_admet.csv
Writes data/compounds_narrated.csv  (original columns + 'groq_memo')
"""

import os
import sys
import time
import textwrap
import pandas as pd

IN_PATH  = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_admet.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "compounds_narrated.csv")

ADMET_COLS = [
    "HIA_Hou",
    "BBB_Martini",
    "CYP3A4_Substrate_CarbonMangels",
    "hERG",
    "DILI",
    "Caco2_Wang",
]

RATE_LIMIT_DELAY = 1.0  # seconds between API calls


def build_prompt(name: str, admet: dict) -> str:
    def fmt(val, is_regression=False):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "N/A"
        if is_regression:
            return f"{val:.3f}"
        prob = float(val)
        label = "positive" if prob >= 0.5 else "negative"
        return f"{prob:.2f} ({label})"

    admet_block = textwrap.dedent(f"""
        - Human intestinal absorption (HIA_Hou):         {fmt(admet.get('HIA_Hou'))}
        - Blood-brain barrier penetration (BBB_Martini): {fmt(admet.get('BBB_Martini'))}
        - CYP3A4 substrate (CYP3A4_Substrate_CarbonMangels): {fmt(admet.get('CYP3A4_Substrate_CarbonMangels'))}
        - hERG cardiotoxicity risk (hERG):               {fmt(admet.get('hERG'))}
        - Drug-induced liver injury risk (DILI):         {fmt(admet.get('DILI'))}
        - Caco-2 permeability log cm/s (Caco2_Wang):     {fmt(admet.get('Caco2_Wang'), is_regression=True)}
    """).strip()

    return textwrap.dedent(f"""
        You are a medicinal chemist writing a concise drug-candidate assessment.
        Write exactly 3 sentences about {name} based on the ADMET data below.
        Sentence 1: absorption and distribution profile (use HIA, BBB, Caco-2 values).
        Sentence 2: metabolism and toxicity risks (use CYP3A4, hERG, DILI values).
        Sentence 3: overall suitability as an oral drug candidate.
        Use precise, scientific language. Do not add bullet points or headings.

        ADMET data for {name}:
        {admet_block}
    """).strip()


def call_groq(client, prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
    )
    memo = response.choices[0].message.content
    return memo.strip()


def init_groq():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print(
            "Error: GROQ_API_KEY environment variable is not set.\n"
            "Export it before running:  export GROQ_API_KEY=your_key_here",
            file=sys.stderr,
        )
        sys.exit(1)

    from groq import Groq
    client = Groq(api_key=api_key)
    print("Groq client initialised (llama-3.1-8b-instant).\n")
    return client


def main():
    if not os.path.exists(IN_PATH):
        print(f"Input file not found: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(IN_PATH)
    print(f"Loaded {len(df)} compounds from {os.path.normpath(IN_PATH)}")

    # Warn about missing ADMET columns but continue — they'll show as N/A in prompt.
    missing = [c for c in ADMET_COLS if c not in df.columns]
    if missing:
        print(f"[WARN] ADMET columns not found in input, will be N/A: {missing}")

    client = init_groq()

    memos = []
    errors = 0

    for i, row in df.iterrows():
        name = row.get("pref_name") or row.get("chembl_id") or f"compound_{i}"
        admet = {col: row.get(col) for col in ADMET_COLS}

        print(f"  [{i+1:>3}/{len(df)}] {name} ...", end=" ", flush=True)

        try:
            prompt = build_prompt(name, admet)
            memo   = call_groq(client, prompt)
            memos.append(memo)
            # Print a truncated preview so progress is meaningful.
            preview = memo[:80].replace("\n", " ")
            print(f'"{preview}..."')
        except Exception as exc:
            print(f"FAILED — {exc}")
            memos.append(None)
            errors += 1

        if i < len(df) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    df["groq_memo"] = memos

    succeeded = df["groq_memo"].notna().sum()
    print(f"\nMemos generated: {succeeded}/{len(df)}  |  Errors: {errors}")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    df.to_csv(OUT_PATH, index=False)
    print(f"Saved to {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
