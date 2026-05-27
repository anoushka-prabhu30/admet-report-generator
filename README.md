# ADMET Drug Report Generator

A Nextflow pipeline that fetches FDA-approved small molecules from ChEMBL, predicts
ADMET properties with ADMET-AI, and uses Google Gemini to narrate each compound's
pharmacokinetic and toxicity profile into a structured HTML report.

---

## Background

Drug discovery is expensive, slow, and fails at an extraordinary rate. Of the
thousands of compounds that enter preclinical development each year, fewer than
10% will ever reach patients. The leading cause of attrition is not lack of
potency — it is **ADMET failure**: poor Absorption, Distribution, Metabolism,
Excretion, and Toxicity profiles that only become apparent late in development,
when the cost of failure is highest.

This phenomenon is sometimes called the **ADMET valley of death**. A compound
may show nanomolar activity against its target in a biochemical assay, yet be
useless as a drug because it is not absorbed orally, is rapidly metabolised by
CYP3A4, accumulates in the brain unexpectedly, or blocks the hERG cardiac
channel at therapeutic concentrations. Historically, roughly **90% of drug
candidates that enter clinical trials fail**, and ADMET-related issues account
for a substantial share of those failures — a proportion that remains stubbornly
high despite decades of medicinal chemistry knowledge.

Computational prediction of ADMET properties has matured considerably with the
advent of large curated datasets (ChEMBL, TDC) and graph-neural-network models
trained on them. Tools like ADMET-AI can now return probability scores for
human intestinal absorption, BBB penetration, CYP3A4 substrate likelihood,
hERG inhibition, and drug-induced liver injury within seconds of receiving a
SMILES string. What these tools produce, however, are **raw numerical scores** —
useful to an expert, but not easily actionable for a broader audience or for
rapid triage across a large compound set.

---

## Research Question

> Can LLM narration of ML-predicted ADMET properties produce human-readable risk
> memos that surface actionable insights beyond what raw probability scores
> communicate on their own?

This project tests whether prompting Gemini 1.5 Flash with a compound's ADMET
scores — framed as a structured medicinal-chemistry briefing — yields coherent,
accurate, and clinically relevant drug-candidate assessments at scale, without
any fine-tuning or retrieval augmentation.

---

## Methods

### 1. Data Fetch (`bin/fetch.py`)
Queries the ChEMBL REST API via `chembl-webresource-client` for 50 FDA-approved
small molecule drugs (`max_phase=4`, `molecule_type=Small molecule`). Retrieves
ChEMBL ID, preferred name, canonical SMILES, molecular weight, and AlogP.
Compounds with missing SMILES are filtered out. Output: `data/compounds.csv`.

### 2. RDKit Featurization (`bin/featurize.py`)
For each SMILES string, computes:
- **Morgan fingerprint** (radius 2, 1024 bits) — stored as flat binary columns `fp_0`…`fp_1023`
- **Physicochemical descriptors**: molecular weight, logP, TPSA, rotatable bonds, H-bond donors/acceptors
- **Lipinski Rule of Five** pass/fail flag

RDKit is used directly for all descriptor calculations. Molecules that cannot be
parsed are skipped and logged. Output: `data/compounds_featurized.csv`.

### 3. ADMET-AI Prediction (`bin/predict.py`)
Runs batch ADMET-AI inference on the `canonical_smiles` column. Extracts six
endpoints relevant to oral drug development:

| Endpoint | Type | Interpretation |
|---|---|---|
| `HIA_Hou` | Classification | Human intestinal absorption |
| `BBB_Martini` | Classification | Blood-brain barrier penetration |
| `CYP3A4_Substrate_CarbonMangels` | Classification | CYP3A4 substrate liability |
| `hERG` | Classification | Cardiac hERG channel inhibition risk |
| `DILI` | Classification | Drug-induced liver injury risk |
| `Caco2_Wang` | Regression (log cm/s) | Caco-2 cell permeability |

Failed predictions fall back to per-molecule mode; remaining failures are stored
as `NaN`. Output: `data/compounds_admet.csv`.

### 4. Gemini Narration (`bin/narrate.py`)
Each compound's name and six ADMET values are formatted into a structured prompt
asking Gemini 1.5 Flash to write a **3-sentence drug-candidate memo**:
- Sentence 1: absorption and distribution profile (HIA, BBB, Caco-2)
- Sentence 2: metabolism and toxicity risks (CYP3A4, hERG, DILI)
- Sentence 3: overall suitability as an oral drug candidate

A 1-second delay is observed between API calls to respect rate limits.
Output: `data/compounds_narrated.csv` with a new `gemini_memo` column.

### 5. HTML Report (`bin/report.py` + `templates/report.html.j2`)
Generates `output/report.html` using Plotly and Jinja2:
- **Summary table** ranking all compounds by a composite ADMET score
  (rewards HIA and Caco-2 permeability; penalises hERG, DILI, CYP3A4 liability)
- **Per-compound card** containing:
  - A Plotly radar chart of the six normalised ADMET dimensions
  - A colour-coded risk table (green / yellow / red per property)
  - The Gemini memo in a styled blockquote

---

## Key Finding

> *Placeholder — run the pipeline and document your findings here.*

Suggested angles to investigate:
- Do the Gemini memos accurately reflect the direction of each ADMET score, or
  does the LLM hallucinate risk levels not supported by the data?
- Which compounds score highest overall and does the memo add nuance beyond
  "good scores = good drug"?
- Are there compounds where individual risk scores conflict (e.g. excellent
  absorption but high hERG risk) and does Gemini surface that tension?

---

## How to Reproduce

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) running on your machine
- [Nextflow](https://www.nextflow.io/docs/latest/install.html) ≥ 23.10
- A Google Gemini API key (free tier is sufficient — see note below)

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/admet-report-generator.git
cd admet-report-generator

# 2. Set your Gemini API key
export GEMINI_API_KEY=your_key_here

# 3. Run the full pipeline
nextflow run main.nf

# 4. Open the report
open output/report.html        # macOS
xdg-open output/report.html   # Linux
```

To re-run only from a specific stage after a failure, Nextflow's `-resume` flag
replays cached work-directory results for unchanged processes:

```bash
nextflow run main.nf -resume
```

To run the Python scripts individually outside Nextflow (useful during development):

```bash
pip install -r requirements.txt

python bin/fetch.py
python bin/featurize.py
python bin/predict.py

export GEMINI_API_KEY=your_key_here
python bin/narrate.py

python bin/report.py
open output/report.html
```

---

## Repository Structure

```
admet-report-generator/
│
├── main.nf                     # Nextflow pipeline (5 processes, DSL2)
├── nextflow.config             # Docker + GEMINI_API_KEY env config
├── requirements.txt            # Python dependencies
│
├── bin/
│   ├── fetch.py                # ChEMBL data fetch → data/compounds.csv
│   ├── featurize.py            # RDKit features → data/compounds_featurized.csv
│   ├── predict.py              # ADMET-AI inference → data/compounds_admet.csv
│   ├── narrate.py              # Gemini narration → data/compounds_narrated.csv
│   └── report.py               # Plotly + Jinja2 report → output/report.html
│
├── templates/
│   └── report.html.j2          # Jinja2 HTML template
│
├── data/                       # Generated CSVs (gitignored)
└── output/                     # Generated HTML report (gitignored)
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `chembl-webresource-client` | ChEMBL REST API client |
| `rdkit` | Molecular featurization and fingerprints |
| `admet-ai` | ADMET property prediction (TDC-trained models) |
| `google-generativeai` | Gemini API client |
| `plotly` | Radar charts in the HTML report |
| `jinja2` | HTML templating |
| `pandas` / `numpy` / `scipy` | Data handling |

---

## Notes

**Gemini API free tier is sufficient.** The narration step makes one API call per
compound (50 calls for the default run). The Gemini 1.5 Flash free tier allows
15 requests per minute and 1,500 requests per day — well within the requirements
of this pipeline. No billing account is needed. Get a key at
[aistudio.google.com](https://aistudio.google.com).

**ADMET-AI model weights** are downloaded automatically on first run and cached
locally by the library. Expect a one-time download of several hundred MB.

**ChEMBL API** is a public REST service; no authentication is required.
