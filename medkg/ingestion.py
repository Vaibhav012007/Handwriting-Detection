from __future__ import annotations
import csv, json
from pathlib import Path
from pydantic import ValidationError
from .models import MedicineRecord
from .repository import CatalogRepository

def load_records(path: str | Path) -> list[dict]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data["medicines"]
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    raise ValueError("catalog must be .json or .csv")

def ingest(path: str | Path, repository: CatalogRepository) -> dict:
    report={"imported":0,"updated":0,"rejected":[],"duplicates":[]}
    seen=set()
    for index, raw in enumerate(load_records(path), 1):
        try:
            record=MedicineRecord.model_validate(raw)
            if record.medicine_id in seen:
                report["duplicates"].append({"row":index,"medicine_id":record.medicine_id}); continue
            seen.add(record.medicine_id)
            report[repository.upsert(record)] += 1
        except (ValidationError, ValueError, KeyError) as exc:
            report["rejected"].append({"row":index,"error":str(exc)})
    return report
