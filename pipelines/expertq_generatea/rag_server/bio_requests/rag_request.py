"""RAG request DTO"""
from pydantic import BaseModel
from typing import List, Optional


class RagRequest(BaseModel):
    """RAG retrieval request"""
    query: str
    top_k: int = 5
    search_type: str = "keyword"
    is_rewrite: bool = False
    data_source: List[str] = ["pubmed"]
    user_id: str = ""
    pubmed_topk: int = 10
    is_rerank: bool = False
    language: str = "en"
