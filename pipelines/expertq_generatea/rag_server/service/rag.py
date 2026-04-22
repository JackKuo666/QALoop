"""RAG service - orchestrates search services"""
import asyncio
import time
from typing import List
from search_service.base_search import BaseSearchService
from dto.bio_document import BaseBioDocument
from bio_requests.rag_request import RagRequest
from utils.bio_logger import bio_logger as logger


class RagService:
    """RAG service orchestrating multiple search services"""

    def __init__(self):
        # Dynamically load all search service subclasses
        self.search_services = [
            subclass() for subclass in BaseSearchService.get_subclasses()
        ]
        logger.info(f"Loaded search services: {[s.__class__.__name__ for s in self.search_services]}")

    async def multi_query(self, rag_request: RagRequest) -> List[BaseBioDocument]:
        """Execute search across all services"""
        start_time = time.time()

        # Execute searches concurrently
        tasks = [service.filter_search(rag_request) for service in self.search_services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Search service error: {result}")
                continue
            all_results.extend(result)

        logger.info(f"Multi-query completed: {len(all_results)} results in {time.time() - start_time:.2f}s")
        return all_results[:rag_request.top_k]
