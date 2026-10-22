"""Evaluation helpers; does not invent metrics or load training data automatically."""
from __future__ import annotations
from .matching import CandidateResolver
from .models import OCRInput

def evaluate_rows(rows: list[dict], resolver: CandidateResolver) -> dict:
    """Evaluate a held-out, labelled list of OCR outputs.

    Each row requires text, ocr_confidence and expected_medicine_id. Optional
    ground_truth_text supports exact OCR word accuracy. Supply a separate test
    set; this function intentionally does not tune thresholds.
    """
    n=len(rows)
    if not n: return {"n":0}
    top1=top3=correct_review=0
    for row in rows:
        outcome=resolver.resolve(OCRInput(text=row["text"], ocr_confidence=row["ocr_confidence"]))
        ids=[c.medicine_id for c in outcome.candidates]
        top1 += bool(ids and ids[0] == row["expected_medicine_id"])
        top3 += row["expected_medicine_id"] in ids[:3]
        if "expected_review_required" in row: correct_review += outcome.review_required == row["expected_review_required"]
    result={"n":n,"top_1_candidate_accuracy":top1/n,"top_3_candidate_accuracy":top3/n}
    if any("expected_review_required" in r for r in rows): result["review_routing_accuracy"]=correct_review/n
    return result
