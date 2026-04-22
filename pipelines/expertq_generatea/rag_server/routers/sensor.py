"""API routes for Bio RAG Server"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from service.rag import RagService
from bio_requests.rag_request import RagRequest
from utils.bio_logger import bio_logger as logger

router = APIRouter()


@router.post("/retrieve")
async def retrieve(rag_request: RagRequest) -> JSONResponse:
    """
    Document retrieval endpoint.

    Request body:
    {
        "query": "search query",
        "top_k": 5,
        "search_type": "keyword",
        "data_source": ["pubmed"],
        "pubmed_topk": 10
    }
    """
    logger.info(f"Retrieve request: query={rag_request.query}")

    try:
        rag_service = RagService()
        documents = await rag_service.multi_query(rag_request)

        results = [doc.__dict__ for doc in documents]
        logger.info(f"Retrieve response: {len(results)} documents")

        return JSONResponse(content={
            "success": True,
            "data": results,
            "message": "Search completed"
        })

    except Exception as e:
        logger.error(f"Retrieve error: {e}")
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


@router.post("/stream-chat")
async def stream_chat(rag_request: RagRequest):
    """
    Streaming chat endpoint (placeholder - requires LLM integration).
    For full streaming chat, integrate with LLM API.
    """
    logger.info(f"Stream chat request: query={rag_request.query}")

    # Placeholder: Return检索结果 in streaming format
    # Full implementation would integrate with LLM for RAG chat
    try:
        rag_service = RagService()
        documents = await rag_service.multi_query(rag_request)

        async def generate():
            for doc in documents:
                yield f"data: {doc.title}\n\n"

        return generate()

    except Exception as e:
        logger.error(f"Stream chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
