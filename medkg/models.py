from __future__ import annotations
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from .normalization import normalize_dosage_form, normalize_text, normalize_unit

class SourceRecord(BaseModel):
    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    url: str | None = None
    dataset_version: str | None = None
    retrieved_on: date | None = None
    license: str | None = None
    source_type: str | None = None
    source_file: str | None = None

class IngredientRecord(BaseModel):
    ingredient_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    terminology_id: str | None = None

class AliasRecord(BaseModel):
    text: str = Field(min_length=1)
    alias_type: str = "brand"
    verified: bool = False
    source_id: str | None = None

class MedicineRecord(BaseModel):
    medicine_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    brand_name: str | None = None
    generic_name: str | None = None
    manufacturer: str | None = None
    strength_value: float | None = Field(default=None, gt=0)
    strength_unit: str | None = None
    dosage_form: str | None = None
    route: str | None = None
    release: str | None = None
    catalog_status: Literal["active", "inactive", "unknown"] = "active"
    source_version: str | None = None
    verification_status: Literal["verified", "source_unverified", "needs_review", "synthetic"] = "source_unverified"
    source: SourceRecord
    ingredients: list[IngredientRecord] = Field(min_length=1)
    aliases: list[AliasRecord] = Field(default_factory=list)

    @field_validator("canonical_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not normalize_text(value):
            raise ValueError("canonical_name must contain searchable text")
        return value.strip()

    @field_validator("strength_unit")
    @classmethod
    def canonical_unit(cls, value: str | None) -> str | None:
        return normalize_unit(value)

    @field_validator("dosage_form")
    @classmethod
    def canonical_form(cls, value: str | None) -> str | None:
        return normalize_dosage_form(value)

class OCRInput(BaseModel):
    text: str = Field(min_length=1, max_length=250)
    ocr_confidence: float = Field(ge=0, le=1)
    strength_value: float | None = Field(default=None, gt=0)
    strength_unit: str | None = None
    dosage_form: str | None = None

class Candidate(BaseModel):
    medicine_id: str
    canonical_name: str
    ingredients: list[str]
    strength_value: float | None = None
    strength_unit: str | None = None
    dosage_form: str | None = None
    text_similarity: float = Field(ge=0, le=100)
    ranking_score: float = Field(ge=0, le=100)
    match_kind: Literal["exact", "verified_alias", "approximate"]
    strength_consistency: Literal["match", "conflict", "unknown"]
    form_consistency: Literal["match", "conflict", "unknown"]
    evidence_complete: bool
    sources: list[SourceRecord]

class Resolution(BaseModel):
    original_text: str
    normalized_text: str
    ocr_confidence: float
    candidates: list[Candidate]
    review_required: bool
    review_reasons: list[str]
    clinical_safety_status: Literal["not_checked", "incomplete", "unknown"] = "not_checked"
