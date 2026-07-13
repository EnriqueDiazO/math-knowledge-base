"""S4.2 logical page maps for persistent PDF Documents."""

from mathmongo.document_page_maps.indexes import DOCUMENT_PAGE_MAPS_COLLECTION
from mathmongo.document_page_maps.indexes import DocumentPageMapIndexManager
from mathmongo.document_page_maps.models import DocumentPageMap
from mathmongo.document_page_maps.models import ManualPageOverride
from mathmongo.document_page_maps.models import PageLabelRule
from mathmongo.document_page_maps.models import PageLabelStyle
from mathmongo.document_page_maps.models import PageMapStatus
from mathmongo.document_page_maps.models import compute_book_page_label
from mathmongo.document_page_maps.repository import DocumentPageMapRepository
from mathmongo.document_page_maps.service import DocumentPageMapService
from mathmongo.document_page_maps.service import PageLabelComputation
from mathmongo.document_page_maps.service import PageLabelMatch
from mathmongo.document_page_maps.service import PageMapOperationStatus
from mathmongo.document_page_maps.service import PageMapServiceResult

__all__ = [
    "DOCUMENT_PAGE_MAPS_COLLECTION",
    "DocumentPageMap",
    "DocumentPageMapIndexManager",
    "DocumentPageMapRepository",
    "DocumentPageMapService",
    "ManualPageOverride",
    "PageLabelComputation",
    "PageLabelMatch",
    "PageLabelRule",
    "PageLabelStyle",
    "PageMapOperationStatus",
    "PageMapServiceResult",
    "PageMapStatus",
    "compute_book_page_label",
]
