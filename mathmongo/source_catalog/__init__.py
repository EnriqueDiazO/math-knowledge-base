"""Source Catalog domain, persistence, and explicit operational services."""

from mathmongo.source_catalog.bibtex import BibTeXParseResult
from mathmongo.source_catalog.bibtex import parse_bibtex_file_content
from mathmongo.source_catalog.bibtex import parse_bibtex_paste
from mathmongo.source_catalog.duplicates import DuplicateClassification
from mathmongo.source_catalog.duplicates import DuplicateMatch
from mathmongo.source_catalog.indexes import SourceCatalogIndexManager
from mathmongo.source_catalog.legacy_repository import LegacyConceptPage
from mathmongo.source_catalog.legacy_repository import LegacyConceptRepository
from mathmongo.source_catalog.legacy_repository import LegacyConceptSummary
from mathmongo.source_catalog.models import Reference
from mathmongo.source_catalog.models import ReferenceAuthor
from mathmongo.source_catalog.models import ReferenceStatus
from mathmongo.source_catalog.models import ReferenceType
from mathmongo.source_catalog.models import Source
from mathmongo.source_catalog.models import SourceStatus
from mathmongo.source_catalog.models import SourceType
from mathmongo.source_catalog.quality import incomplete_reference_fields
from mathmongo.source_catalog.repository import ReferenceRepository
from mathmongo.source_catalog.repository import SourceRepository
from mathmongo.source_catalog.service import CatalogResult
from mathmongo.source_catalog.service import CatalogResultStatus
from mathmongo.source_catalog.service import SourceCatalogService

__all__ = [
    "BibTeXParseResult",
    "CatalogResult",
    "CatalogResultStatus",
    "DuplicateClassification",
    "DuplicateMatch",
    "LegacyConceptPage",
    "LegacyConceptRepository",
    "LegacyConceptSummary",
    "Reference",
    "ReferenceAuthor",
    "ReferenceRepository",
    "ReferenceStatus",
    "ReferenceType",
    "Source",
    "SourceCatalogIndexManager",
    "SourceCatalogService",
    "SourceRepository",
    "SourceStatus",
    "SourceType",
    "incomplete_reference_fields",
    "parse_bibtex_file_content",
    "parse_bibtex_paste",
]
