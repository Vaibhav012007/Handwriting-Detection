from __future__ import annotations
from abc import ABC, abstractmethod
import logging
from .models import MedicineRecord, SourceRecord
from .normalization import normalize_text

logger=logging.getLogger(__name__)

class CatalogRepository(ABC):
    @abstractmethod
    def upsert(self, record: MedicineRecord) -> str: ...
    @abstractmethod
    def all_medicines(self) -> list[MedicineRecord]: ...
    @abstractmethod
    def evidence(self, medicine_id: str) -> dict | None: ...
    @abstractmethod
    def graph_stats(self) -> dict: ...
    def health(self) -> dict: return {"backend": self.__class__.__name__, "ready": True, **self.graph_stats()}

class InMemoryCatalogRepository(CatalogRepository):
    """Test/development repository. It never claims that its data are clinical."""
    def __init__(self): self.records: dict[str, MedicineRecord] = {}
    def upsert(self, record: MedicineRecord) -> str:
        result = "updated" if record.medicine_id in self.records else "imported"
        self.records[record.medicine_id] = record
        return result
    def all_medicines(self) -> list[MedicineRecord]: return list(self.records.values())
    def graph_stats(self) -> dict:
        medicines=self.all_medicines()
        return {"database":"in_memory_development", "medicine_nodes":len(medicines),
          "ingredient_nodes":len({i.ingredient_id for m in medicines for i in m.ingredients}),
          "alias_nodes":sum(len(m.aliases) for m in medicines),
          "source_nodes":len({m.source.source_id for m in medicines}),
          "relationship_count":sum(1+len(m.ingredients)+len(m.aliases) for m in medicines)}
    def evidence(self, medicine_id: str) -> dict | None:
        record = self.records.get(medicine_id)
        if not record: return None
        return {"medicine": record, "sources": [record.source], "clinical_facts": [],
                "relationships":["Medicine-HAS_INGREDIENT->Ingredient" for _ in record.ingredients] + ["Medicine-SUPPORTED_BY->Source"],
                "warning": "No clinical safety conclusion is available from this catalog."}

class Neo4jCatalogRepository(CatalogRepository):
    """Neo4j implementation using parameterized Cypher. Requires neo4j extra."""
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database
    def _session(self): return self.driver.session(database=self.database)
    def close(self): self.driver.close()
    def health(self) -> dict:
        try:
            self.driver.verify_connectivity()
            return {"backend": "neo4j", "ready": True, **self.graph_stats()}
        except Exception as exc:
            logger.warning("Neo4j connectivity check failed: %s", type(exc).__name__)
            return {"backend": "neo4j", "ready": False, "detail": type(exc).__name__}
    def initialize_schema(self):
        statements = [
            "CREATE CONSTRAINT medicine_id IF NOT EXISTS FOR (n:Medicine) REQUIRE n.medicine_id IS UNIQUE",
            "CREATE CONSTRAINT ingredient_id IF NOT EXISTS FOR (n:Ingredient) REQUIRE n.ingredient_id IS UNIQUE",
            "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.source_id IS UNIQUE",
            "CREATE CONSTRAINT alias_key IF NOT EXISTS FOR (n:Alias) REQUIRE n.alias_key IS UNIQUE",
            "CREATE INDEX medicine_normalized IF NOT EXISTS FOR (n:Medicine) ON (n.normalized_name)",
        ]
        with self._session() as s:
            for statement in statements: s.run(statement).consume()
    def upsert(self, record: MedicineRecord) -> str:
        before = any(x.medicine_id == record.medicine_id for x in self.all_medicines())
        payload = record.model_dump(mode="json")
        query = """
        MERGE (m:Medicine {medicine_id:$medicine_id})
        SET m += $medicine, m.normalized_name=$normalized_name
        MERGE (s:Source {source_id:$source.source_id}) SET s += $source
        MERGE (m)-[:SUPPORTED_BY]->(s)
        WITH m
        UNWIND $ingredients AS ingredient
        MERGE (i:Ingredient {ingredient_id:ingredient.ingredient_id}) SET i += ingredient
        MERGE (m)-[:HAS_INGREDIENT]->(i)
        WITH m
        UNWIND $aliases AS alias
        MERGE (a:Alias {alias_key:$medicine_id + '|' + alias.normalized_text}) SET a += alias
        MERGE (a)-[:ALIAS_OF]->(m)
        """
        aliases = [{**a, "normalized_text": normalize_text(a["text"])} for a in payload["aliases"]]
        medicine = {k:v for k,v in payload.items() if k not in {"source", "ingredients", "aliases"}}
        with self._session() as s:
            s.run(query, medicine_id=record.medicine_id, medicine=medicine,
                  normalized_name=normalize_text(record.canonical_name), source=payload["source"],
                  ingredients=payload["ingredients"], aliases=aliases).consume()
        return "updated" if before else "imported"
    def all_medicines(self) -> list[MedicineRecord]:
        query = """MATCH (m:Medicine)-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (m)-[:HAS_INGREDIENT]->(i:Ingredient)
        OPTIONAL MATCH (a:Alias)-[:ALIAS_OF]->(m)
        RETURN m, s, collect(DISTINCT i) AS ingredients, collect(DISTINCT a) AS aliases"""
        records=[]
        with self._session() as session:
            for row in session.run(query):
                m=dict(row["m"]); records.append(MedicineRecord(**m, source=dict(row["s"]),
                    ingredients=[dict(i) for i in row["ingredients"] if i], aliases=[dict(a) for a in row["aliases"] if a]))
        return records
    def evidence(self, medicine_id: str) -> dict | None:
        query="""MATCH (m:Medicine {medicine_id:$medicine_id})-[:SUPPORTED_BY]->(s:Source)
        OPTIONAL MATCH (m)-[:HAS_INGREDIENT]->(i:Ingredient)
        OPTIONAL MATCH (a:Alias)-[:ALIAS_OF]->(m)
        RETURN m, s, collect(DISTINCT i) AS ingredients, collect(DISTINCT a) AS aliases"""
        with self._session() as session:
            row=session.run(query, medicine_id=medicine_id).single()
        if not row: return None
        record=MedicineRecord(**dict(row["m"]), source=dict(row["s"]),
          ingredients=[dict(i) for i in row["ingredients"] if i], aliases=[dict(a) for a in row["aliases"] if a])
        return {"medicine":record,"sources":[record.source],"clinical_facts":[],
          "relationships":["Medicine-HAS_INGREDIENT->Ingredient" for _ in record.ingredients] + ["Medicine-SUPPORTED_BY->Source"]}
    def graph_stats(self) -> dict:
        query="""CALL () { MATCH (m:Medicine) RETURN count(m) AS medicines }
        CALL () { MATCH (i:Ingredient) RETURN count(i) AS ingredients }
        CALL () { MATCH (a:Alias) RETURN count(a) AS aliases }
        CALL () { MATCH ()-[r]->() RETURN count(r) AS relationships }
        RETURN medicines, ingredients, aliases, relationships"""
        with self._session() as session: row=session.run(query).single()
        return {"database":self.database,"medicine_nodes":row["medicines"],"ingredient_nodes":row["ingredients"],
          "alias_nodes":row["aliases"],"relationship_count":row["relationships"]}
