# Knowledge graph extension architecture

`pipeline.py` remains the OCR boundary: it preprocesses a word crop, invokes
TrOCR, and exposes a string plus aggregate OCR confidence. `medkg.api.run_ocr`
adapts that existing interface without assuming regions or token scores.

```text
image -> existing TrOCR -> OCRMention-compatible response -> CandidateResolver
                                                   |                 |
                                              OCR confidence     CatalogRepository
                                                                     |-- memory (dev/test)
                                                                     `-- Neo4j (configured)
```

Neo4j identities are constrained for `Medicine.medicine_id`,
`Ingredient.ingredient_id`, `Source.source_id`, and `Alias.alias_key`.
The importer upserts Medicine, Ingredient, Source and Alias nodes and links
`HAS_INGREDIENT`, `SUPPORTED_BY`, and `ALIAS_OF`; it uses parameters rather
than string interpolation. An `OCRMention` and review history are represented
in API results for the MVP but deliberately retained only in application
memory; production deployment needs a protected application database and
authentication before handling patient records.

No interaction or contraindication relationship is seeded. A future clinical
import must add only provenance-backed `ClinicalFact` data and should create
`INTERACTS_WITH` only from the provider's licensed, versioned evidence.
