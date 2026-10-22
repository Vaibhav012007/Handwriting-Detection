"""Import an explicitly supplied verified catalog file into Neo4j."""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from medkg.ingestion import ingest
from medkg.repository import Neo4jCatalogRepository

p=argparse.ArgumentParser(); p.add_argument("catalog"); args=p.parse_args()
repo=Neo4jCatalogRepository(os.environ["NEO4J_URI"], os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"], os.getenv("NEO4J_DATABASE", "neo4j"))
try:
    repo.initialize_schema(); print(ingest(args.catalog, repo))
finally: repo.close()
