"""Knowledge-graph-backed medicine catalogue extension.

This package deliberately keeps clinical catalog data separate from the OCR
training labels.  It is safe to run with its in-memory repository for local
development and tests; Neo4j is selected only when configured.
"""

from .models import MedicineRecord

__all__ = ["MedicineRecord"]
