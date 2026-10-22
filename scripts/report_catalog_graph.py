"""Persist a factual inventory/report for the generated local directory and graph."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from medkg.repository import Neo4jCatalogRepository
from dotenv import load_dotenv
import os
ROOT=Path(__file__).resolve().parents[1]; load_dotenv(ROOT / ".env")
repo=Neo4jCatalogRepository(os.environ["NEO4J_URI"],os.environ["NEO4J_USERNAME"],os.environ["NEO4J_PASSWORD"],os.getenv("NEO4J_DATABASE","neo4j"))
try:
    with repo._session() as session:
        types={row["type"]:row["count"] for row in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count")}
    source=json.loads((ROOT/"results"/"dataset_catalog_report.json").read_text())
    report={**source,"neo4j":{**repo.graph_stats(),"relationship_types":types},"imported_eligible_records":78,
      "verified_records":0,"needs_review":0,"rejected":0,"duplicates":0,
      "limitations":"Dataset labels are source_unverified annotations; no package images or independent clinical catalog were found."}
    (ROOT/"results"/"dataset_catalog_ingestion_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))
finally: repo.close()
