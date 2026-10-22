from rapidfuzz import fuzz
from .models import Candidate, OCRInput, Resolution
from .normalization import normalize_text, normalize_dosage_form, normalize_unit
from .repository import CatalogRepository

class CandidateResolver:
    def __init__(self, repository: CatalogRepository, approximate_floor: float = 55.0):
        self.repository, self.approximate_floor = repository, approximate_floor
    def resolve(self, request: OCRInput, limit: int = 5) -> Resolution:
        query=normalize_text(request.text); candidates=[]
        try:
            medicines=self.repository.all_medicines()
        except Exception:
            return Resolution(original_text=request.text, normalized_text=query, ocr_confidence=request.ocr_confidence,
              candidates=[], review_required=True, review_reasons=["catalog_unavailable"], clinical_safety_status="not_checked")
        for med in medicines:
            names=[(med.canonical_name, "exact" if normalize_text(med.canonical_name)==query else "approximate")]
            names += [(a.text, "verified_alias") for a in med.aliases if a.verified]
            best_name, kind, score=max(((name, k, fuzz.ratio(query,normalize_text(name))) for name,k in names), key=lambda x:x[2])
            if score < self.approximate_floor: continue
            if normalize_text(best_name)==query: score=100.0
            strength = "unknown" if request.strength_value is None else ("match" if request.strength_value == med.strength_value and normalize_unit(request.strength_unit)==med.strength_unit else "conflict")
            form = "unknown" if not request.dosage_form else ("match" if normalize_dosage_form(request.dosage_form)==med.dosage_form else "conflict")
            penalty = 25 if "conflict" in (strength,form) else 0
            candidates.append(Candidate(medicine_id=med.medicine_id, canonical_name=med.canonical_name,
              ingredients=[i.name for i in med.ingredients], strength_value=med.strength_value, strength_unit=med.strength_unit,
              dosage_form=med.dosage_form, text_similarity=round(score,2), ranking_score=round(max(0,score-penalty),2),
              match_kind=kind if score < 100 else ("exact" if normalize_text(med.canonical_name)==query else kind),
              strength_consistency=strength, form_consistency=form, evidence_complete=bool(med.ingredients and med.source), sources=[med.source]))
        candidates.sort(key=lambda c:c.ranking_score, reverse=True); candidates=candidates[:limit]
        reasons=[]
        if not medicines: reasons.append("catalog_unpopulated")
        elif not candidates: reasons.append("no_catalog_candidate")
        if request.ocr_confidence < .70: reasons.append("low_ocr_reliability_demo_threshold")
        if len(candidates)>1 and candidates[0].ranking_score-candidates[1].ranking_score < 8: reasons.append("multiple_plausible_candidates")
        if any(c.strength_consistency=="conflict" or c.form_consistency=="conflict" for c in candidates): reasons.append("conflicting_strength_or_form")
        return Resolution(original_text=request.text, normalized_text=query, ocr_confidence=request.ocr_confidence,
          candidates=candidates, review_required=bool(reasons), review_reasons=reasons,
          clinical_safety_status="incomplete" if candidates else "not_checked")
