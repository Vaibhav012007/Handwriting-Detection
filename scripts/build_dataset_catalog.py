"""Build a traceable, non-clinically-verified catalog from project label CSVs."""
import csv, hashlib, json, sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from medkg.normalization import normalize_text

SPLITS=("train","val","test")
rows=[]
for split in SPLITS:
    with (ROOT / "data" / "raw" / split / "labels.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows.extend({**row,"split":split} for row in csv.DictReader(handle))
by_brand=defaultdict(set)
for row in rows: by_brand[row["MEDICINE_NAME"].strip()].add(row["GENERIC_NAME"].strip())
records=[]; review=[]
for brand,generics in sorted(by_brand.items(), key=lambda item: normalize_text(item[0])):
    if len(generics)!=1:
        review.append({"brand_name":brand,"generic_labels":sorted(generics),"reason":"conflicting_dataset_labels"}); continue
    generic=next(iter(generics)); token=hashlib.sha256(normalize_text(brand).encode()).hexdigest()[:12].upper()
    ingredient=hashlib.sha256(normalize_text(generic).encode()).hexdigest()[:12].upper()
    records.append({"medicine_id":f"DATASET-BRAND-{token}","canonical_name":brand,"brand_name":brand,"generic_name":generic,
      "catalog_status":"unknown","source_version":"project-labels-1","verification_status":"source_unverified",
      "source":{"source_id":"PROJECT-PRESCRIPTION-LABELS","name":"Doctor's Handwritten Prescription BD dataset labels","dataset_version":"project-labels-1","license":"Unknown; verify before redistribution","source_type":"handwritten_prescription_annotation","source_file":"data/raw/{train,val,test}/labels.csv","retrieved_on":str(date.today())},
      "ingredients":[{"ingredient_id":f"DATASET-GENERIC-{ingredient}","name":generic}],"aliases":[]})
out=ROOT / "catalog" / "dataset_derived_catalog.json"; out.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
report={"files_scanned":3,"structured_datasets":3,"prescription_images":len(rows),"medicine_packaging_images":0,"rows":len(rows),"unique_brands":len(records),"unique_generic_labels":len({next(iter(v)) for v in by_brand.values() if len(v)==1}),"conflicts":len(review),"verification":"source_unverified"}
(ROOT / "results" / "dataset_catalog_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
(ROOT / "results" / "dataset_catalog_review.json").write_text(json.dumps(review,indent=2)+"\n",encoding="utf-8")
print(json.dumps(report))
