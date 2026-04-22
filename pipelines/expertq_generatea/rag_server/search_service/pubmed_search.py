"""PubMed search service using Biopython Entrez - no ES required"""
from typing import List
from search_service.base_search import BaseSearchService
from service.pubmed_api import PubMedApi
from dto.bio_document import PubMedDocument
from bio_requests.rag_request import RagRequest
from utils.bio_logger import bio_logger as logger


class PubMedSearchService(BaseSearchService):
    """PubMed search using Biopython Entrez API"""

    def __init__(self):
        self.pubmed_api = PubMedApi()
        self.data_source = "pubmed"

    async def search(self, rag_request: RagRequest) -> List[PubMedDocument]:
        """Search PubMed database"""
        if not rag_request.query:
            return []

        logger.info(f"PubMedSearchService searching: {rag_request.query}")

        try:
            results = self.pubmed_api.search(
                query=rag_request.query,
                top_k=rag_request.pubmed_topk or 10,
                search_type=rag_request.search_type or "keyword"
            )
            logger.info(f"PubMedSearchService found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"PubMedSearchService error: {e}")
            return []
