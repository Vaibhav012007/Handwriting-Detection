"""Opt-in live Neo4j proof; never runs against an unconfigured database."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from medkg.api import app, configure_repository
from medkg.ingestion import ingest
from medkg.matching import CandidateResolver
from medkg.models import OCRInput
from medkg.repository import InMemoryCatalogRepository, Neo4jCatalogRepository

pytestmark=pytest.mark.skipif(os.getenv("RUN_NEO4J_INTEGRATION") != "1", reason="set RUN_NEO4J_INTEGRATION=1 with a disposable Neo4j database")
FIXTURE=Path(__file__).parents[1] / "catalog" / "neo4j_integration_fixture.json"

def test_real_neo4j_catalog_path_and_api():
    repo=Neo4jCatalogRepository(os.environ["NEO4J_URI"],os.environ["NEO4J_USERNAME"],os.environ["NEO4J_PASSWORD"],os.getenv("NEO4J_DATABASE","neo4j"))
    try:
        repo.initialize_schema(); report=ingest(FIXTURE,repo); assert report["imported"] in (0,1) and not report["rejected"]
        evidence=repo.evidence("TEST-MED-001")
        assert evidence and evidence["medicine"].ingredients[0].ingredient_id == "TEST-ING-001"
        assert "Medicine-HAS_INGREDIENT->Ingredient" in evidence["relationships"]
        resolved=CandidateResolver(repo).resolve(OCRInput(text="Test Product Alpha",ocr_confidence=.99))
        assert resolved.candidates[0].medicine_id == "TEST-MED-001"
        # A separate driver lets the FastAPI lifespan close its own resource
        # while this repository remains available for narrowly-scoped cleanup.
        api_repo=Neo4jCatalogRepository(os.environ["NEO4J_URI"],os.environ["NEO4J_USERNAME"],os.environ["NEO4J_PASSWORD"],os.getenv("NEO4J_DATABASE","neo4j"))
        configure_repository(api_repo)
        with TestClient(app) as client:
            response=client.get("/medicines/search",params={"q":"Test Product Alpha"})
        assert response.status_code == 200 and response.json()["candidates"][0]["medicine_id"] == "TEST-MED-001"
    finally:
        # The exact stable test identifier keeps cleanup scoped to fixture data.
        with repo._session() as session:
            session.run("MATCH (m:Medicine {medicine_id:$id}) DETACH DELETE m",id="TEST-MED-001").consume()
            session.run("MATCH (n) WHERE n.source_id=$source OR n.ingredient_id=$ingredient DETACH DELETE n",source="TEST-SOURCE-001",ingredient="TEST-ING-001").consume()
        repo.close(); configure_repository(InMemoryCatalogRepository())
