import json
from pathlib import Path
from medkg.ingestion import ingest
from medkg.matching import CandidateResolver
from medkg.models import OCRInput
from medkg.repository import InMemoryCatalogRepository

FIXTURE=Path(__file__).parents[1] / "catalog" / "synthetic_catalog.json"

def populated():
    repo=InMemoryCatalogRepository(); report=ingest(FIXTURE, repo); return repo, report

def test_ingestion_is_idempotent():
    repo, report=populated(); assert report["imported"] == 2
    report=ingest(FIXTURE, repo); assert report["updated"] == 2 and len(repo.all_medicines()) == 2

def test_invalid_record_is_rejected(tmp_path):
    path=tmp_path / "bad.json"; path.write_text(json.dumps([{"medicine_id":"x"}]))
    report=ingest(path, InMemoryCatalogRepository()); assert len(report["rejected"]) == 1

def test_verified_alias_and_strength_conflict_route_to_review():
    repo,_=populated(); outcome=CandidateResolver(repo).resolve(OCRInput(text="Aceta", ocr_confidence=.95, strength_value=650, strength_unit="mg"))
    assert outcome.candidates[0].match_kind == "verified_alias"
    assert outcome.review_required and "conflicting_strength_or_form" in outcome.review_reasons

def test_misspelling_and_no_candidate():
    repo,_=populated(); resolver=CandidateResolver(repo)
    assert resolver.resolve(OCRInput(text="Acetaa", ocr_confidence=.9)).candidates
    assert not resolver.resolve(OCRInput(text="zzzzunlikely", ocr_confidence=.9)).candidates

def test_empty_catalog_is_not_reported_as_complete_no_match():
    outcome=CandidateResolver(InMemoryCatalogRepository()).resolve(OCRInput(text="Anything", ocr_confidence=.9))
    assert outcome.review_reasons == ["catalog_unpopulated"]
