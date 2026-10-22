"""FastAPI integration. Run with: uvicorn medkg.api:app --reload.

The in-memory prescription store is intentionally development-only; production
review/audit data should be stored in a protected application database.
"""
from __future__ import annotations
import io, os, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from .models import OCRInput
from .matching import CandidateResolver
from .repository import InMemoryCatalogRepository, Neo4jCatalogRepository
from .ingestion import ingest
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

MAX_UPLOAD_BYTES=8*1024*1024
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if isinstance(_repo, Neo4jCatalogRepository):
        _repo.close()

app=FastAPI(title="Prescription Knowledge Graph API", version="0.1.0", lifespan=lifespan)
def _initial_repository():
    if os.getenv("MEDKG_REPOSITORY", "memory").casefold() == "neo4j":
        required=("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD")
        missing=[name for name in required if not os.getenv(name)]
        if missing: raise RuntimeError(f"Missing Neo4j settings: {', '.join(missing)}")
        repo=Neo4jCatalogRepository(os.environ["NEO4J_URI"], os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"], os.getenv("NEO4J_DATABASE", "neo4j"))
        repo.initialize_schema()
        return repo
    return InMemoryCatalogRepository()

_repo=_initial_repository()
_resolver=CandidateResolver(_repo)
_prescriptions: dict[str, dict] = {}

# A clearly labelled fixture makes the API demonstrable out of the box. Replace
# this with a licensed/verified catalog before any real-world use.
_synthetic = os.path.join(os.path.dirname(os.path.dirname(__file__)), "catalog", "synthetic_catalog.json")
if isinstance(_repo, InMemoryCatalogRepository) and os.path.exists(_synthetic):
    ingest(_synthetic, _repo)

class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(confirmed|corrected|unresolved|escalated)$")
    selected_medicine_id: str | None = None
    corrected_text: str | None = Field(default=None, max_length=250)
    reviewer_id: str | None = Field(default=None, max_length=100)

def configure_repository(repository) -> None:
    """Dependency seam used by application startup and tests."""
    global _repo, _resolver
    if repository is not _repo and isinstance(_repo, Neo4jCatalogRepository):
        _repo.close()
    _repo, _resolver = repository, CandidateResolver(repository)

@app.get("/health")
def health():
    catalog=_repo.health()
    return {"status":"ok" if catalog["ready"] else "degraded", "api":"ok", "neo4j":"connected" if catalog["backend"]=="neo4j" and catalog["ready"] else ("not_configured" if catalog["backend"]!="neo4j" else "unavailable"),
      "catalog":catalog, "prescription_store":"development_memory"}

@app.get("/medicines/search")
def search_medicines(q: str, limit: int=5):
    if not q.strip(): raise HTTPException(422, "q must not be blank")
    if not 1 <= limit <= 20: raise HTTPException(422, "limit must be between 1 and 20")
    return _resolver.resolve(OCRInput(text=q, ocr_confidence=1.0), limit).model_dump()

@app.get("/medicines/{medicine_id}/evidence")
def medicine_evidence(medicine_id: str):
    evidence=_repo.evidence(medicine_id)
    if not evidence: raise HTTPException(404, "medicine not found")
    return {k:(v.model_dump() if hasattr(v,"model_dump") else [x.model_dump() if hasattr(x,"model_dump") else x for x in v] if isinstance(v,list) else v) for k,v in evidence.items()}

def run_ocr(image: Image.Image) -> tuple[str,float]:
    """Adapter preserving the existing TrOCR inference interface."""
    from pipeline import run_trocr_robust
    return run_trocr_robust(image)

@app.post("/prescriptions", status_code=201)
async def create_prescription(image: UploadFile = File(...)):
    if image.content_type not in {"image/png","image/jpeg","image/webp"}:
        raise HTTPException(415, "only PNG, JPEG, and WebP images are accepted")
    data=await image.read(MAX_UPLOAD_BYTES+1)
    if len(data)>MAX_UPLOAD_BYTES: raise HTTPException(413, "image exceeds 8 MiB limit")
    try:
        pil_image=Image.open(io.BytesIO(data)); pil_image.verify()
        pil_image=Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "invalid image file")
    try: text, confidence=run_ocr(pil_image)
    except Exception as exc:
        raise HTTPException(503, "OCR model is unavailable") from exc
    resolution=_resolver.resolve(OCRInput(text=text or "[empty]", ocr_confidence=confidence))
    prescription_id=str(uuid.uuid4())
    _prescriptions[prescription_id]={"id":prescription_id,"created_at":datetime.now(timezone.utc).isoformat(),
        "recognition":resolution.model_dump(),"review":{"status":"pending"}}
    return _prescriptions[prescription_id]

@app.get("/prescriptions/{prescription_id}")
def get_prescription(prescription_id: str):
    item=_prescriptions.get(prescription_id)
    if not item: raise HTTPException(404, "prescription not found")
    return item

@app.post("/prescriptions/{prescription_id}/review")
def review_prescription(prescription_id: str, review: ReviewRequest):
    item=_prescriptions.get(prescription_id)
    if not item: raise HTTPException(404, "prescription not found")
    if review.selected_medicine_id and not _repo.evidence(review.selected_medicine_id):
        raise HTTPException(422, "selected medicine does not exist in catalog")
    item["review"]={**review.model_dump(), "reviewed_at":datetime.now(timezone.utc).isoformat()}
    # Corrections are review data, never automatically converted into aliases.
    return item

_dashboard=os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_dashboard):
    app.mount("/", StaticFiles(directory=_dashboard, html=True), name="dashboard")
