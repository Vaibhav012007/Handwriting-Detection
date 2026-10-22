# Medical Prescription Recognition Pipeline

This repository contains a full machine-learning pipeline for recognising handwritten medicine names from prescription word-crops.

## Features

- **Preprocessing & Augmentation**: Advanced OpenCV filtering (CLAHE, median blur) to restore faded ink, plus TorchVision augmentations (perspective, rotation) tailored for handwriting.
- **TrOCR Fine-tuning**: Fine-tunes Microsoft's TrOCR (Transformer-based Optical Character Recognition) to read cursive handwriting.
- **Mask R-CNN Scaffold**: Architecture ready for region detection (word-crop passthrough mode enabled by default since the current dataset only provides cropped words).
- **Fuzzy Dictionary Matching**: Uses Levenshtein distance and RapidFuzz to correct OCR errors by matching against a known database of 78 medicine brands and mapping them to their generic equivalents.

## Installation

Create a virtual environment and install the dependencies:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Dataset Setup

1. Place your data in `data/raw/` (or run `python setup_data.py` if you have the original `archive__6_.zip` to partition it into train/val/test splits).
2. Ensure the directory structure looks like this:
```
data/
└── raw/
    ├── train/
    │   ├── images/
    │   └── labels.csv
    ├── val/
    │   ├── images/
    │   └── labels.csv
    └── test/
        ├── images/
        └── labels.csv
```

## Usage

### 1. Exploratory Data Analysis (EDA)
Check the dataset balance and verify there is no data leakage between splits using Perceptual Hashing.
```bash
python eda.py
```
*Results are saved in the `results/` folder.*

### 2. Train the OCR Model
Fine-tune the TrOCR model on the training set. This script supports early stopping and logs validation CER (Character Error Rate).
```bash
python train_trocr.py
```
*The best model is saved to `checkpoints/trocr_best/`.*

### 3. Evaluate the Pipeline
Evaluates the model on the `test` split. First tunes the optimal confidence threshold on the `val` split, then applies dictionary matching and calculates ablation metrics.
```bash
python evaluate.py
```
*Generates `results/metrics.json` and a full ablation table.*

### 4. Run Inference on New Images
Run the end-to-end pipeline on a single image or a folder of images.
```bash
python pipeline.py --image path/to/image.png
# OR
python pipeline.py --image path/to/folder/
```
*Outputs are appended to `results/predictions.csv` and `results/predictions.jsonl`.*

## Project Structure
- `common.py` - Core preprocessing, data augmentation, and dataset loading logic.
- `train_trocr.py` - TrOCR training loop with evaluation callbacks.
- `train_maskrcnn.py` - Mask R-CNN scaffold (passthrough mode).
- `matcher.py` - Fuzzy dictionary matching and confidence computation.
- `evaluate.py` - Full test-set evaluation and metrics generation.
- `pipeline.py` - Inference CLI for end-to-end structured prediction.
- `REPORT.md` - Technical report template.

## Knowledge Graph catalog extension (MVP)

The original OCR pipeline is unchanged. `medkg/` adds a separate product
catalog, candidate resolver, review policy, FastAPI service, and optional Neo4j
repository. OCR is currently word-crop based: `pipeline.run_trocr_robust()`
returns one recognised string plus an aggregate generation confidence. It does
not return token confidence, patient data, or reliable text bounding boxes.

The default API includes only `catalog/synthetic_catalog.json`, explicitly
labelled non-clinical test data. It is not medicine advice and must be replaced
with a licensed, verified catalog before real use. In particular, a missing
clinical fact is reported as unknown and never as safe.

Install the added packages, then run tests and the API:

```bash
pip install -r requirements.txt
pytest -q
uvicorn medkg.api:app --reload
```

Open `frontend/index.html` through the same protected deployment, or use
`GET /medicines/search?q=Aceta`. The upload endpoint is `POST /prescriptions`;
it accepts an image, invokes the existing TrOCR adapter, and returns OCR and
candidate scores separately. It requires the existing TrOCR checkpoint.

### Neo4j

```bash
docker compose up -d neo4j
copy .env.example .env
# Edit .env and set a local Neo4j password before first `docker compose up`.
python scripts/init_graph.py
python scripts/ingest_catalog.py catalog/synthetic_catalog.json
uvicorn medkg.api:app --reload
```

`scripts/ingest_catalog.py` accepts JSON following the documented template.
It validates Pydantic records, normalizes names/units/forms, upserts stable
identifiers, records catalog source provenance, and reports imports, updates,
duplicates, and rejected rows. Neo4j constraints cover Medicine, Ingredient,
Source and Alias identities. All Cypher values are parameterized.

Use licensed sources appropriate to the deployed geography. RxNorm can provide
US terminology mappings but does not cover all Indian marketed products; an
Indian catalog must be obtained directly under its provider's terms. No web
catalog is scraped by this project. Clinical interaction/contraindication facts
are deliberately not shipped: the graph has space for source-backed facts but
does not make unsupported safety assertions.

### Review policy and limits

`medkg.matching.CandidateResolver` checks exact names, verified aliases, then
RapidFuzz similarity. Similarity is a retrieval score, not a probability;
OCR reliability, text similarity, rank, strength/form consistency, evidence,
and safety state remain separate fields. The temporary 0.70 OCR review trigger
is a demonstration setting, not clinically validated. Calibrate it only on a
held-out labelled validation set. `medkg.evaluate.evaluate_rows` can report
Top-1/Top-3 and review-routing measurements from such a set; it creates no
metrics itself.

`GET /health` reports actual counts for the configured catalog backend. With
`MEDKG_REPOSITORY=neo4j`, it also checks driver connectivity and the selected
`NEO4J_DATABASE`; a degraded health result must be treated as no catalog, not
as a legitimate no-match result. The default in-memory fixture has only two
synthetic Aceta records, so unrelated OCR such as `Azyth` correctly produces
no candidate.

### Build the local dataset-derived directory

The included prescription-label CSVs provide 78 brand-to-generic annotations,
but no independently verified product strengths, forms, manufacturers, or
licenses. Build their traceable directory with:

```bash
python scripts/build_dataset_catalog.py
python scripts/ingest_catalog.py catalog/dataset_derived_catalog.json
```

Records are imported as `source_unverified`, have no invented strength/form,
and retain the CSV source provenance. Review results are written under
`results/dataset_catalog_*`; these labels must not be treated as authoritative
clinical product data.
